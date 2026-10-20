import { describe, expect, it } from 'vitest';

import { getAIErrorMessage } from './aiErrors';

describe('getAIErrorMessage', () => {
  it.each([
    ['AI_SERVICE_DISABLED', 'AI 服务尚未启用，请联系管理员完成服务器配置。'],
    ['AI_ACCESS_DENIED', 'Cloudflare Access 验证失败，请管理员检查服务器凭据和访问策略。'],
    ['AI_TUNNEL_UNAVAILABLE', '远程 AI 服务暂时不可用，请稍后重试或检查 Tunnel 状态。'],
    ['AI_CONNECT_TIMEOUT', '连接 AI 服务超时，请检查服务地址和网络连接。'],
    ['AI_RESPONSE_TIMEOUT', 'AI 模型响应超时，模型可能仍在启动，请稍后重试。'],
    ['AI_MODEL_ERROR', 'AI 模型配置或请求参数有误，请检查默认模型。'],
    ['AI_UPSTREAM_ERROR', '上游 AI 服务异常，请稍后重试。'],
    ['AI_RESPONSE_INVALID', 'AI 返回内容格式不正确，未应用本次推荐。'],
  ])('maps %s to a stable Chinese message', (code, message) => {
    expect(getAIErrorMessage({ response: { data: { error: { code } } } })).toBe(message);
  });

  it.each([
    [{ response: { status: 403, data: { detail: 'sensitive permission detail' } } }],
    [{ response: { status: 500, data: { error: { code: 'HTTP_ERROR', details: { status: 403 }, message: 'secret' } } } }],
  ])('maps administrator permission changes without exposing details', (error) => {
    const message = getAIErrorMessage(error);

    expect(message).toBe('权限已变更，当前操作仅限管理员，请重新登录或联系管理员。');
    expect(message).not.toContain('sensitive');
    expect(message).not.toContain('secret');
  });

  it('uses a bounded generic fallback without exposing upstream details', () => {
    const marker = 'upstream-secret-response-marker';
    const message = getAIErrorMessage({
      message: marker.repeat(100),
      response: {
        data: {
          error: {
            code: 'UNRECOGNIZED_AI_FAILURE',
            message: marker.repeat(100),
            details: { upstream: marker.repeat(100) },
          },
        },
      },
    });

    expect(message).toBe('AI 服务暂时不可用，请稍后重试；图书信息仍可手工填写和保存。');
    expect(message.length).toBeLessThanOrEqual(40);
    expect(message).not.toContain(marker);
  });
});
