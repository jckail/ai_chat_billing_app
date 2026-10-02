export const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

export function chatSocketUrl(apiUrl, userId, threadId) {
  const url = new URL(apiUrl, window.location.origin);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
    throw new Error('Configure an HTTP or HTTPS API URL without credentials.');
  }
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = `/ws/chat/${encodeURIComponent(userId)}/${encodeURIComponent(threadId)}`;
  url.search = '';
  url.hash = '';
  return url.toString();
}

export function messageId(message) {
  return message.id ?? message.message_id ?? message.messageId;
}

export function formatCurrency(amount) {
  const number = Number(amount);
  return amount !== null && amount !== undefined && Number.isFinite(number) ? `$${number.toFixed(6)}` : 'Not available';
}

export function tokenCount(message) {
  if (Number.isFinite(message.token_count)) return message.token_count;
  if (Number.isFinite(message.tokens)) return message.tokens;
  if (Array.isArray(message.tokens)) return message.tokens.reduce((sum, token) => sum + (Number.isFinite(token.token_count) ? token.token_count : 0), 0);
  return null;
}
