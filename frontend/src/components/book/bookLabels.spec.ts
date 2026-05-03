import { describe, expect, it } from 'vitest';

import {
  getBookStatusLabel,
  getBookStatusTagType,
  getReadStatusLabel,
  getReadStatusTagType,
} from './bookLabels';

describe('book label helpers', () => {
  it('maps book statuses to display labels', () => {
    expect(getBookStatusLabel('available')).toBe('在架');
    expect(getBookStatusLabel('borrowed')).toBe('借出');
    expect(getBookStatusLabel('lost')).toBe('遗失');
    expect(getBookStatusLabel('pending')).toBe('待整理');
    expect(getBookStatusLabel('gifted')).toBe('已转赠');
  });

  it('maps read statuses to display labels', () => {
    expect(getReadStatusLabel('unread')).toBe('未读');
    expect(getReadStatusLabel('reading')).toBe('阅读中');
    expect(getReadStatusLabel('read')).toBe('已读');
    expect(getReadStatusLabel('paused')).toBe('暂停');
  });

  it('keeps tag types stable for table and card rendering', () => {
    expect(getBookStatusTagType('available')).toBe('success');
    expect(getBookStatusTagType('borrowed')).toBe('warning');
    expect(getBookStatusTagType('lost')).toBe('danger');
    expect(getReadStatusTagType('read')).toBe('success');
    expect(getReadStatusTagType('reading')).toBe('warning');
  });
});
