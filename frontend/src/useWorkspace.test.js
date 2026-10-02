import { act, renderHook, waitFor } from '@testing-library/react';
import axios from 'axios';
import useWorkspace from './useWorkspace';
jest.mock('axios');

const threads = [{ thread_id: 1, title: 'One' }, { thread_id: 2, title: 'Two' }];
const metrics = id => ({ thread_id: id, total_messages: 0, total_input_tokens: 0, total_output_tokens: 0, total_cost: 0 });
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
class Socket {
  static OPEN = 1;
  static instances = [];
  constructor(url) { this.url = url; this.readyState = 0; this.send = jest.fn(); Socket.instances.push(this); }
  open() { this.readyState = 1; this.onopen?.(); }
  emit(data) { this.onmessage?.({ data: JSON.stringify(data) }); }
  close() { this.readyState = 3; this.onclose?.(); }
}
beforeEach(() => {
  Socket.instances = []; global.WebSocket = Socket;
  axios.get.mockImplementation(url => Promise.resolve({ data: url.includes('/threads?') ? threads : url.includes('/history') ? [] : metrics(Number(url.match(/thread\/(\d+)/)?.[1])) }));
  axios.post.mockReset();
});
afterEach(() => { jest.useRealTimers(); jest.clearAllMocks(); });
async function ready() {
  const hook = renderHook(() => useWorkspace());
  await waitFor(() => expect(hook.result.current.currentThread?.thread_id).toBe(1));
  await waitFor(() => expect(hook.result.current.threadMetrics?.thread_id).toBe(1));
  return hook;
}

test('failed HTTP send retains draft and exposes recovery guidance', async () => {
  const { result } = await ready();
  axios.post.mockRejectedValueOnce(new Error('offline'));
  act(() => result.current.setNewMessage('keep this draft'));
  await act(async () => result.current.sendMessage());
  expect(result.current.newMessage).toBe('keep this draft');
  expect(result.current.error).toMatch(/could not be sent/);
  expect(result.current.loading).toBe(false);
});

test('drafts belong to each thread; late history, metrics and socket callbacks cannot replace selection', async () => {
  const history = deferred(); const usage = deferred();
  axios.get.mockImplementation(url => {
    if (url.includes('/threads?')) return Promise.resolve({ data: threads });
    if (url.includes('/messages/1/')) return history.promise;
    if (url.includes('/metrics/thread/1')) return usage.promise;
    return Promise.resolve({ data: url.includes('/history') ? [{ id: 22, role: 'assistant', content: 'Second thread' }] : metrics(2) });
  });
  const { result } = renderHook(() => useWorkspace());
  await waitFor(() => expect(result.current.currentThread?.thread_id).toBe(1));
  const firstSocket = Socket.instances[0];
  act(() => { result.current.setNewMessage('first draft'); result.current.setCurrentThread(threads[1]); });
  await waitFor(() => expect(result.current.threadMetrics?.thread_id).toBe(2));
  act(() => result.current.setNewMessage('second draft'));
  await act(async () => {
    history.resolve({ data: [{ id: 11, content: 'Stale first thread' }] }); usage.resolve({ data: metrics(1) });
    firstSocket.emit({ type: 'THREAD_CONNECTED', history: [{ id: 12, content: 'Stale socket' }] });
    firstSocket.onclose();
  });
  expect(result.current.messages[0].content).toBe('Second thread');
  expect(result.current.threadMetrics.thread_id).toBe(2);
  expect(result.current.wsStatus).toBe('connecting');
  await act(async () => result.current.setCurrentThread(threads[0]));
  expect(result.current.newMessage).toBe('first draft');
});

test('assistant completion refreshes metrics for the connected thread', async () => {
  const { result } = await ready();
  jest.useFakeTimers();
  const socket = Socket.instances[0];
  act(() => { socket.open(); socket.emit({ type: 'ASSISTANT_COMPLETE', message: { id: 5, role: 'assistant', content: 'Done' } }); });
  axios.get.mockClear();
  await act(async () => { jest.advanceTimersByTime(5000); });
  expect(axios.get).toHaveBeenCalledWith(expect.stringContaining('/billing/metrics/thread/1?refresh=true'));
  expect(result.current.messages[0].content).toBe('Done');
});

test('billing retry exhaustion resolves to a visible error and can recover', async () => {
  const { result } = await ready();
  jest.useFakeTimers();
  axios.get.mockRejectedValue(new Error('offline'));
  let refresh;
  await act(async () => { refresh = result.current.fetchThreadMetrics(1, true); });
  for (let n = 0; n < 3; n += 1) await act(async () => { jest.advanceTimersByTime(2000); });
  await act(async () => { await refresh; });
  expect(result.current.metricsError).toMatch(/could not load/);
  expect(result.current.refreshingMetrics).toBe(false);
  axios.get.mockResolvedValue({ data: metrics(1) });
  await act(async () => result.current.fetchThreadMetrics(1, true));
  expect(result.current.metricsError).toBeNull();
});

test('socket acknowledgment replaces optimistic message with authoritative server data', async () => {
  const { result } = await ready(); const socket = Socket.instances[0];
  act(() => socket.open());
  act(() => result.current.setNewMessage('Hello'));
  await act(async () => result.current.sendMessage());
  expect(result.current.messages).toHaveLength(1);
  act(() => socket.emit({ type: 'MESSAGE_SENT', message: { id: 42, role: 'user', content: 'Hello', tokens: 2 } }));
  expect(result.current.messages).toEqual([{ id: 42, role: 'user', content: 'Hello', tokens: 2 }]);
  expect(axios.post).not.toHaveBeenCalled();
});


test('a sent message whose history fails is not presented as a failed send', async () => {
  const { result } = await ready();
  axios.post.mockResolvedValueOnce({ data: {} });
  axios.get.mockRejectedValueOnce(new Error('history unavailable'));
  act(() => result.current.setNewMessage('Send once'));
  await act(async () => result.current.sendMessage());
  expect(result.current.newMessage).toBe('');
  expect(result.current.error).toMatch(/message was sent/);
  expect(axios.post).toHaveBeenCalledTimes(1);
});


test('initial socket history preserves a message sent while connecting history arrives', async () => {
  const { result } = await ready(); const socket = Socket.instances[0];
  act(() => socket.open());
  act(() => result.current.setNewMessage('Keep optimistic message'));
  await act(async () => result.current.sendMessage());
  act(() => socket.emit({ type: 'THREAD_CONNECTED', history: [{ id: 2, role: 'assistant', content: 'Earlier history' }] }));
  expect(result.current.messages).toHaveLength(2);
  act(() => socket.emit({ type: 'MESSAGE_SENT', message: { id: 3, role: 'user', content: 'Keep optimistic message' } }));
  expect(result.current.messages[1].id).toBe(3);
});
