const AI_ERROR_MESSAGES: Record<string, string> = {
  AI_SERVICE_DISABLED: 'AI 服务尚未启用，请联系管理员完成服务器配置。',
  AI_ACCESS_DENIED: 'Cloudflare Access 验证失败，请管理员检查服务器凭据和访问策略。',
  AI_TUNNEL_UNAVAILABLE: '远程 AI 服务暂时不可用，请稍后重试或检查 Tunnel 状态。',
  AI_CONNECT_TIMEOUT: '连接 AI 服务超时，请检查服务地址和网络连接。',
  AI_RESPONSE_TIMEOUT: 'AI 模型响应超时，模型可能仍在启动，请稍后重试。',
  AI_MODEL_ERROR: 'AI 模型配置或请求参数有误，请检查默认模型。',
  AI_UPSTREAM_ERROR: '上游 AI 服务异常，请稍后重试。',
  AI_RESPONSE_INVALID: 'AI 返回内容格式不正确，未应用本次推荐。',
};

const GENERIC_AI_ERROR = 'AI 服务暂时不可用，请稍后重试；图书信息仍可手工填写和保存。';

export function getAIErrorMessage(error: unknown): string {
  if (!error || typeof error !== 'object' || !('response' in error)) {
    return GENERIC_AI_ERROR;
  }

  const response = (error as { response?: { data?: { error?: { code?: unknown } } } }).response;
  const code = response?.data?.error?.code;
  return typeof code === 'string' && AI_ERROR_MESSAGES[code]
    ? AI_ERROR_MESSAGES[code]
    : GENERIC_AI_ERROR;
}
