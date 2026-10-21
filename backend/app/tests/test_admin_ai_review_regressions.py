"""Regression contracts for the final managed-server configuration review."""
from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.security import verify_admin_secondary_auth
from app.models import SystemAISetting, SystemConfigAudit
from app.services.credential_crypto import CredentialCryptoError, is_production_secret_key
from app.services.system_ai_setting_service import CredentialUpdate, update_server_ai_config
from app.tests.conftest import make_user
from app.tests.test_system_ai_setting_service import _clear_ai_environment, _values
from app.tests.test_system_ai_settings_api import _auth_headers, _put, _delete, _valid_update


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _documented_key():
    lines = (Path(__file__).parents[3] / 'docs/deployment.md').read_text().splitlines()
    return next(line.split('=', 1)[1].strip() for line in lines if line.startswith('APP_SECRET_KEY='))


@pytest.mark.parametrize('padding', ['', ' \t', '\n  '], ids=['plain', 'spaces', 'newline'])
def test_public_documented_key_is_rejected(padding):
    assert not is_production_secret_key(padding + _documented_key() + padding)
    assert is_production_secret_key(secrets.token_urlsafe(48))


def test_public_key_service_refuses_pair_without_writes_but_allows_preserve_clear(db, monkeypatch):
    _clear_ai_environment(monkeypatch)
    monkeypatch.setenv('APP_SECRET_KEY', _documented_key())
    get_settings.cache_clear()
    with pytest.raises(CredentialCryptoError):
        update_server_ai_config(db, values=_values(), credentials=CredentialUpdate(
            mode='replace_pair', client_id=secrets.token_hex(20), client_secret=secrets.token_hex(20)), actor_id=1)
    assert db.query(SystemAISetting).count() == db.query(SystemConfigAudit).count() == 0
    for mode in ('preserve', 'clear_pair'):
        assert update_server_ai_config(db, values=_values(), credentials=CredentialUpdate(mode=mode), actor_id=1)


def test_public_key_api_rejects_pair_without_writes(client, db, monkeypatch):
    _clear_ai_environment(monkeypatch)
    monkeypatch.setenv('APP_SECRET_KEY', _documented_key())
    monkeypatch.setenv('UPGRADE_PASSWORD', 'review-upgrade-password')
    get_settings.cache_clear()
    headers, _ = _auth_headers(db)
    response = _put(client, headers, _valid_update(upgrade_password='review-upgrade-password',
        access_client_id=secrets.token_hex(20), access_client_secret=secrets.token_hex(20)))
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'AI_SERVER_CREDENTIAL_ERROR'
    assert db.query(SystemAISetting).count() == db.query(SystemConfigAudit).count() == 0


@pytest.mark.parametrize('case', ['unicode_match', 'unicode_wrong', 'ascii_match', 'ascii_unicode_wrong', 'unencodable'])
def test_secondary_auth_compares_encoded_passwords(db, monkeypatch, case):
    admin, password = make_user(db, role='admin')
    configured = '升级专用口令' if case.startswith('unicode') else 'ascii-upgrade-password'
    submitted = configured if case.endswith('match') else ('\ud800' if case == 'unencodable' else '错误口令')
    monkeypatch.setenv('UPGRADE_PASSWORD', configured)
    get_settings.cache_clear()
    if case.endswith('match'):
        verify_admin_secondary_auth(admin, SecretStr(password), SecretStr(submitted))
    else:
        with pytest.raises(HTTPException) as caught:
            verify_admin_secondary_auth(admin, SecretStr(password), SecretStr(submitted))
        assert caught.value.status_code == 403
        assert submitted not in str(caught.value)


@pytest.mark.parametrize('operation', ['put', 'delete'])
def test_unicode_auth_rejection_has_no_write_side_effects(client, db, monkeypatch, operation):
    monkeypatch.setenv('UPGRADE_PASSWORD', '服务器升级口令')
    get_settings.cache_clear()
    headers, _ = _auth_headers(db)
    payload = _valid_update(upgrade_password='错误输入')
    response = _put(client, headers, payload) if operation == 'put' else _delete(client, headers, {
        'admin_password': payload['admin_password'], 'upgrade_password': payload['upgrade_password'], 'confirm_reset': True})
    assert response.status_code == 403
    assert '错误输入' not in response.text
    assert db.query(SystemAISetting).count() == db.query(SystemConfigAudit).count() == 0


def test_disabled_models_exception_graph_drops_credentials_and_records_failure(db, monkeypatch):
    import asyncio
    from app.api.routes import ai
    from app.core.errors import ApiError
    from app.models.ai_task import AITask
    from app.services.ai_setting_service import OllamaRuntimeConfig
    from app.tests.test_ai import _assert_route_exception_graph_excludes

    markers = (secrets.token_hex(24), secrets.token_hex(24))
    _clear_ai_environment(monkeypatch)
    monkeypatch.setenv('OLLAMA_ENABLED', 'false')
    monkeypatch.setenv('OLLAMA_CF_ACCESS_CLIENT_ID', markers[0])
    monkeypatch.setenv('OLLAMA_CF_ACCESS_CLIENT_SECRET', markers[1])
    get_settings.cache_clear()
    user, _ = make_user(db)
    real_client = ai.OllamaClient
    constructed = []

    def forbidden_client(*args, **kwargs):
        constructed.append(True)
        raise AssertionError('disabled models must not construct a network client')

    monkeypatch.setattr(ai, 'OllamaClient', forbidden_client)
    with pytest.raises(ApiError) as caught:
        asyncio.run(ai.list_models(db, user))
    assert caught.value.code == 'AI_SERVICE_DISABLED'
    assert caught.value.status_code == 503
    assert not constructed
    task = db.query(AITask).one()
    assert task.task_type == 'models' and task.status == 'failed'
    assert all(marker not in str(task.__dict__) for marker in markers)
    _assert_route_exception_graph_excludes(caught.value, *markers,
        forbidden_types=(OllamaRuntimeConfig, real_client))


@pytest.mark.parametrize('operation', ['update', 'reset'])
def test_database_constraint_failure_is_safe_and_rolls_back(db, monkeypatch, caplog, operation):
    import logging
    from sqlalchemy import event
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session
    from app.services import system_ai_setting_service as service
    from app.services.credential_crypto import CredentialCipher
    from app.tests.test_ai import _assert_route_exception_graph_excludes

    _clear_ai_environment(monkeypatch)
    monkeypatch.setenv('APP_SECRET_KEY', secrets.token_urlsafe(48))
    get_settings.cache_clear()
    admin, _ = make_user(db, role='admin')
    actor_id = admin.id
    db.commit()
    db.connection().exec_driver_sql('PRAGMA foreign_keys=ON')
    old_pair = (secrets.token_hex(24), secrets.token_hex(24))
    service.update_server_ai_config(db, values=_values(default_model='before-failure'),
        credentials=CredentialUpdate(mode='replace_pair', client_id=old_pair[0], client_secret=old_pair[1]), actor_id=actor_id)
    row = db.get(SystemAISetting, 1)
    old_ciphertexts = (row.access_client_id_ciphertext, row.access_client_secret_ciphertext)
    old_version = row.config_version
    audit_count = db.query(SystemConfigAudit).count()
    markers = (secrets.token_hex(24), secrets.token_hex(24))
    ciphertexts = []
    real_encrypt = CredentialCipher.encrypt

    def capture_ciphertext(self, plaintext):
        result = real_encrypt(self, plaintext)
        ciphertexts.append(result)
        return result

    monkeypatch.setattr(CredentialCipher, 'encrypt', capture_ciphertext)
    actual_errors = []

    def observe_real_constraint(context):
        # Record only safe metadata; never retain the DB error or SQL params.
        actual_errors.append((type(context.sqlalchemy_exception).__name__,
            all(value in str(context.sqlalchemy_exception) for value in ciphertexts)))

    event.listen(db.bind, 'handle_error', observe_real_constraint)
    try:
        try:
            if operation == 'update':
                service.update_server_ai_config(db, values=_values(default_model='must-rollback'),
                    credentials=CredentialUpdate(mode='replace_pair', client_id=markers[0], client_secret=markers[1]), actor_id=actor_id + 10000)
            else:
                service.reset_server_ai_config(db, actor_id=actor_id + 10000)
        except Exception as caught:
            failure = caught
        else:
            pytest.fail('real FK violation must fail')
    finally:
        event.remove(db.bind, 'handle_error', observe_real_constraint)
    assert actual_errors and actual_errors[0][0] == 'IntegrityError'
    if operation == 'update':
        assert len(ciphertexts) == 2 and actual_errors[0][1]
    db.expire_all()
    retained = db.get(SystemAISetting, 1)
    assert retained.default_model == 'before-failure' and retained.config_version == old_version
    assert (retained.access_client_id_ciphertext, retained.access_client_secret_ciphertext) == old_ciphertexts
    assert db.query(SystemConfigAudit).count() == audit_count
    assert type(failure).__name__ == 'ServerAIConfigWriteError'
    _assert_route_exception_graph_excludes(failure, *markers, *old_pair, *ciphertexts, *old_ciphertexts,
        forbidden_types=(SQLAlchemyError, Session, SystemAISetting, CredentialUpdate))
    with caplog.at_level(logging.ERROR):
        logging.getLogger('review.sanitized').error('write failed', exc_info=(type(failure), failure, failure.__traceback__))
    assert all(marker not in caplog.text for marker in (*markers, *ciphertexts, *old_ciphertexts))


@pytest.mark.parametrize('operation', ['update', 'reset'])
def test_database_route_failure_has_safe_response_and_exception_graph(db, monkeypatch, client, caplog, operation):
    from sqlalchemy import event
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session
    from starlette.requests import Request
    from app.api.routes import system_ai_settings as routes
    from app.core.errors import ApiError
    from app.schemas.system_ai_setting import SystemAIConfigUpdateRequest, SystemAIConfigResetRequest
    from app.services.credential_crypto import CredentialCipher
    from app.tests.test_ai import _assert_route_exception_graph_excludes

    monkeypatch.setenv('APP_SECRET_KEY', secrets.token_urlsafe(48))
    monkeypatch.setenv('UPGRADE_PASSWORD', 'review-upgrade-password')
    get_settings.cache_clear()
    headers, actor_id = _auth_headers(db)
    from app.models import User
    admin = db.get(User, actor_id)
    db.commit()
    db.connection().exec_driver_sql('PRAGMA foreign_keys=ON')
    markers = (secrets.token_hex(24), secrets.token_hex(24))
    raw = _valid_update(upgrade_password='review-upgrade-password', access_client_id=markers[0], access_client_secret=markers[1])
    assert _put(client, headers, raw).status_code == 200
    old_row = db.get(SystemAISetting, 1)
    old_ciphertexts = (old_row.access_client_id_ciphertext, old_row.access_client_secret_ciphertext)
    count = db.query(SystemConfigAudit).count()
    actual_errors, ciphertexts = [], []
    original_encrypt = CredentialCipher.encrypt

    def capture_ciphertext(self, plaintext):
        result = original_encrypt(self, plaintext)
        ciphertexts.append(result)
        return result

    monkeypatch.setattr(CredentialCipher, 'encrypt', capture_ciphertext)

    def invalidate_actor(session, *_):
        for obj in session.new | session.dirty:
            if isinstance(obj, SystemAISetting):
                obj.updated_by = actor_id + 10000
            elif isinstance(obj, SystemConfigAudit):
                obj.created_by = actor_id + 10000

    def record_error(context):
        actual_errors.append(type(context.sqlalchemy_exception).__name__)

    invalidations = []
    monkeypatch.setattr(routes.ai_health_status_cache, 'invalidate_all', lambda: invalidations.append(True))
    event.listen(db, 'before_flush', invalidate_actor)
    event.listen(db.bind, 'handle_error', record_error)
    request = Request({'type': 'http', 'scheme': 'https', 'server': ('library.test', 443), 'path': '/', 'headers': []})
    reset_payload = {'admin_password': raw['admin_password'], 'upgrade_password': raw['upgrade_password'], 'confirm_reset': True}
    try:
        with pytest.raises(ApiError) as caught:
            if operation == 'update':
                routes.put_system_ai_config(request, SystemAIConfigUpdateRequest(**raw), db, admin)
            else:
                routes.delete_system_ai_config(request, SystemAIConfigResetRequest(**reset_payload), db, admin)
        assert caught.value.code == 'AI_SERVER_CONFIG_WRITE_FAILED'
        assert caught.value.status_code == 500
        _assert_route_exception_graph_excludes(caught.value, *markers, *ciphertexts, *old_ciphertexts,
            forbidden_types=(SQLAlchemyError, Session, SystemAISetting, CredentialUpdate, SystemAIConfigUpdateRequest, SystemAIConfigResetRequest))
        response = _put(client, headers, raw) if operation == 'update' else _delete(client, headers, reset_payload)
        assert response.status_code == 500
        assert response.json()['error']['code'] == 'AI_SERVER_CONFIG_WRITE_FAILED'
        assert all(value not in response.text + caplog.text for value in (*markers, *ciphertexts, *old_ciphertexts))
        assert not invalidations
        assert len(actual_errors) == 2 and set(actual_errors) == {'IntegrityError'}
        assert db.query(SystemConfigAudit).count() == count
        retained = db.get(SystemAISetting, 1)
        assert (retained.access_client_id_ciphertext, retained.access_client_secret_ciphertext) == old_ciphertexts
    finally:
        event.remove(db, 'before_flush', invalidate_actor)
        event.remove(db.bind, 'handle_error', record_error)


def test_rollback_failure_does_not_export_original_database_error(db, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session
    from app.tests.test_ai import _assert_route_exception_graph_excludes

    _clear_ai_environment(monkeypatch)
    monkeypatch.setenv('APP_SECRET_KEY', secrets.token_urlsafe(48))
    get_settings.cache_clear()
    db.connection().exec_driver_sql('PRAGMA foreign_keys=ON')
    markers = (secrets.token_hex(24), secrets.token_hex(24))
    def fail_rollback():
        raise RuntimeError(markers[1])
    monkeypatch.setattr(db, 'rollback', fail_rollback)
    with pytest.raises(Exception) as caught:
        update_server_ai_config(db, values=_values(), credentials=CredentialUpdate(
            mode='replace_pair', client_id=markers[0], client_secret=markers[1]), actor_id=10000)
    assert type(caught.value).__name__ == 'ServerAIConfigWriteError'
    _assert_route_exception_graph_excludes(caught.value, *markers,
        forbidden_types=(SQLAlchemyError, Session, SystemAISetting, CredentialUpdate))
    assert not db.in_transaction()


@pytest.mark.parametrize('operation', ['update', 'reset', 'create'])
def test_interleaved_writers_keep_one_complete_valid_configuration(tmp_path, monkeypatch, operation):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.schemas.system_ai_setting import SystemAIConfigUpdateRequest
    from app.services import system_ai_setting_service as service

    _clear_ai_environment(monkeypatch)
    monkeypatch.setenv('APP_SECRET_KEY', secrets.token_urlsafe(48))
    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path / 'review-writers.sqlite'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    a, b, reader = sessions(), sessions(), sessions()
    pair = (secrets.token_hex(24), secrets.token_hex(24))
    initial = SystemAIConfigUpdateRequest(**_valid_update(connect_timeout_seconds=20, read_timeout_seconds=180))
    request_a = SystemAIConfigUpdateRequest(**_valid_update(connect_timeout_seconds=40, read_timeout_seconds=180))
    request_b = SystemAIConfigUpdateRequest(**_valid_update(connect_timeout_seconds=20, read_timeout_seconds=30,
        access_client_id=pair[0], access_client_secret=pair[1]))
    if operation != 'create':
        service.update_server_ai_config(a, values=initial.update_values(), credentials=initial.credential_update(), actor_id=1)
    committed = []
    @event.listens_for(a, 'before_commit', once=True)
    def commit_b_before_a(_):
        committed.append(service.update_server_ai_config(b, values=request_b.update_values(),
            credentials=request_b.credential_update(), actor_id=2))
    try:
        try:
            if operation == 'reset':
                service.reset_server_ai_config(a, actor_id=1)
            else:
                service.update_server_ai_config(a, values=request_a.update_values(), credentials=request_a.credential_update(), actor_id=1)
        except Exception as caught:
            failure = caught
        else:
            failure = None
        final = service.get_effective_server_ai_config(reader)
        assert committed
        assert (final.connect_timeout_seconds, final.read_timeout_seconds) == (20, 30)
        assert final.connect_timeout_seconds < final.read_timeout_seconds
        assert type(failure).__name__ == 'ServerAIConfigConflictError'
        row = reader.get(SystemAISetting, 1)
        from app.services.credential_crypto import CredentialCipher
        cipher = CredentialCipher.from_secret_key(get_settings().secret_key)
        assert (cipher.decrypt(row.access_client_id_ciphertext), cipher.decrypt(row.access_client_secret_ciphertext)) == pair
        audits = reader.query(SystemConfigAudit).all()
        assert len(audits) == (1 if operation == 'create' else 2)
        assert all(audit.action == 'update' for audit in audits)
        assert row.config_version == committed[0].config_version
    finally:
        a.close()
        b.close()
        reader.close()
        engine.dispose()


@pytest.mark.parametrize('operation', ['put_preserve', 'put_replace', 'put_clear', 'delete', 'create'])
def test_api_concurrent_conflict_is_409_without_audit_or_cache_side_effects(tmp_path, monkeypatch, operation):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session, sessionmaker
    from starlette.requests import Request
    from app.api.routes import system_ai_settings as routes
    from app.core.errors import ApiError
    from app.models import Base
    from app.schemas.system_ai_setting import SystemAIConfigUpdateRequest, SystemAIConfigResetRequest
    from app.services import system_ai_setting_service as service
    from app.tests.test_ai import _assert_route_exception_graph_excludes

    _clear_ai_environment(monkeypatch)
    monkeypatch.setenv('APP_SECRET_KEY', secrets.token_urlsafe(48))
    monkeypatch.setenv('UPGRADE_PASSWORD', 'review-upgrade-password')
    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path / 'review-api-conflict.sqlite'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    a, b, reader = sessions(), sessions(), sessions()
    admin, _ = make_user(a, role='admin', password='review-admin-password')
    actor_id = admin.id
    markers = (secrets.token_hex(24), secrets.token_hex(24))
    raw = _valid_update(admin_password='review-admin-password', upgrade_password='review-upgrade-password',
        connect_timeout_seconds=40, read_timeout_seconds=180)
    if operation == 'put_replace':
        raw.update(access_client_id=markers[0], access_client_secret=markers[1])
    elif operation == 'put_clear':
        raw.update(clear_access_credentials=True)
    if operation != 'create':
        service.update_server_ai_config(a, values=_values(connect_timeout_seconds=20, read_timeout_seconds=180),
            credentials=CredentialUpdate(mode='replace_pair', client_id=markers[0], client_secret=markers[1]), actor_id=actor_id)
    invalidations = []
    monkeypatch.setattr(routes.ai_health_status_cache, 'invalidate_all', lambda: invalidations.append(True))
    winner_pair = (secrets.token_hex(24), secrets.token_hex(24))
    @event.listens_for(a, 'before_commit', once=True)
    def commit_b_before_a(_):
        service.update_server_ai_config(b, values=_values(connect_timeout_seconds=20, read_timeout_seconds=30),
            credentials=CredentialUpdate(mode='replace_pair', client_id=winner_pair[0], client_secret=winner_pair[1]), actor_id=actor_id)
    request = Request({'type': 'http', 'scheme': 'https', 'server': ('library.test', 443), 'path': '/', 'headers': []})
    try:
        with pytest.raises(ApiError) as caught:
            if operation == 'delete':
                routes.delete_system_ai_config(request, SystemAIConfigResetRequest(
                    admin_password=raw['admin_password'], upgrade_password=raw['upgrade_password'], confirm_reset=True), a, admin)
            else:
                routes.put_system_ai_config(request, SystemAIConfigUpdateRequest(**raw), a, admin)
        assert caught.value.status_code == 409 and caught.value.code == 'AI_SERVER_CONFIG_CONFLICT'
        _assert_route_exception_graph_excludes(caught.value, *markers, *winner_pair,
            forbidden_types=(Session, SystemAISetting, CredentialUpdate))
        assert not invalidations
        assert reader.query(SystemConfigAudit).count() == (1 if operation == 'create' else 2)
        final = service.get_effective_server_ai_config(reader)
        assert (final.connect_timeout_seconds, final.read_timeout_seconds) == (20, 30)
        from app.services.ai_setting_service import get_ollama_runtime_config
        runtime = get_ollama_runtime_config(reader, None)
        assert (runtime.access_client_id, runtime.access_client_secret) == winner_pair
    finally:
        a.close()
        b.close()
        reader.close()
        engine.dispose()
