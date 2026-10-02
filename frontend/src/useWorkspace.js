import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { API_BASE_URL, chatSocketUrl, messageId } from './endpoints';

// This development prototype uses a seeded account, not an authenticated identity.
const DEMO_USER = { user_id: 1, username: 'testuser', email: 'test@example.com' };
const MODEL_ID = 1;

export default function useWorkspace() {
  const user = DEMO_USER;
  const [threads, setThreads] = useState([]);
  const [currentThread, setCurrentThread] = useState(null);
  const [messages, setMessages] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [loading, setLoading] = useState(false);
  const [creatingThread, setCreatingThread] = useState(false);
  const [loadingThreads, setLoadingThreads] = useState(false);
  const [threadsError, setThreadsError] = useState(null);
  const [error, setError] = useState(null);
  const [wsStatus, setWsStatus] = useState('disconnected');
  const [typing, setTyping] = useState(false);
  const [tabValue, setTabValue] = useState(0);
  const [threadMetrics, setThreadMetrics] = useState(null);
  const [metricsError, setMetricsError] = useState(null);
  const [metricsUpdatedAt, setMetricsUpdatedAt] = useState(null);
  const [refreshingMetrics, setRefreshingMetrics] = useState(false);
  const selectedId = currentThread?.thread_id ?? null;
  const selectedIdRef = useRef(null);
  selectedIdRef.current = selectedId;
  const wsRef = useRef(null);
  const metricsRequestRef = useRef(0);
  const threadRequestRef = useRef(0);
  const timersRef = useRef(new Set());
  const creatingRef = useRef(false);
  const sendingRef = useRef(false);
  const messageSequenceRef = useRef(0);
  const selectionGenerationRef = useRef(0);

  const fetchThreads = useCallback(async () => {
    const request = ++threadRequestRef.current;
    setLoadingThreads(true);
    setThreadsError(null);
    try {
      const response = await axios.get(`${API_BASE_URL}/threads?user_id=${DEMO_USER.user_id}`);
      if (request !== threadRequestRef.current) return;
      setThreads(response.data);
      setCurrentThread(previous => previous || response.data[0] || null);
    } catch {
      if (request === threadRequestRef.current) setThreadsError('Threads could not load. Try refreshing the list.');
    } finally {
      if (request === threadRequestRef.current) setLoadingThreads(false);
    }
  }, []);

  const fetchThreadMetrics = useCallback(async (threadId, refresh = false) => {
    if (selectedIdRef.current !== threadId) return;
    const request = ++metricsRequestRef.current;
    const active = () => request === metricsRequestRef.current && selectedIdRef.current === threadId;
    setRefreshingMetrics(true);
    setMetricsError(null);
    try {
      for (let attempt = 0; attempt < 4; attempt += 1) {
        if (!active()) return;
        try {
          const response = await axios.get(`${API_BASE_URL}/billing/metrics/thread/${threadId}${refresh ? '?refresh=true' : ''}`);
          if (!active()) return;
          const data = response.data;
          if (data.total_input_tokens === 0 && data.total_output_tokens === 0 && data.total_messages > 0 && attempt < 3) {
            refresh = true;
            await new Promise(resolve => setTimeout(resolve, 3000));
            continue;
          }
          setThreadMetrics(data);
          setMetricsUpdatedAt(new Date());
          return;
        } catch {
          if (!active()) return;
          if (attempt === 3) {
            setMetricsError('Usage metrics could not load. Try again.');
            return;
          }
          await new Promise(resolve => setTimeout(resolve, 2000));
        }
      }
    } finally {
      if (active()) setRefreshingMetrics(false);
    }
  }, []);

  const scheduleMetrics = useCallback((threadId, delay) => {
    const timer = setTimeout(() => {
      timersRef.current.delete(timer);
      if (selectedIdRef.current === threadId) fetchThreadMetrics(threadId, true);
    }, delay);
    timersRef.current.add(timer);
  }, [fetchThreadMetrics]);

  useEffect(() => {
    fetchThreads();
    return () => { threadRequestRef.current += 1; };
  }, [fetchThreads, user.user_id]);

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    let socketHistory = false;
    const pendingMessages = [];
    const timers = timersRef.current;
    let ws;
    let ping;
    const threadId = selectedId;
    selectionGenerationRef.current += 1;
    setMessages([]);
    setThreadMetrics(null);
    setMetricsError(null);
    setMetricsUpdatedAt(null);
    setError(null);
    setTyping(false);
    setWsStatus('connecting');
    fetchThreadMetrics(threadId);

    axios.get(`${API_BASE_URL}/messages/${threadId}/history`).then(response => {
      if (active && !socketHistory && !ws?.historyAdvanced) setMessages(response.data);
    }).catch(() => {
      if (active && !socketHistory && !ws?.historyAdvanced) setError('Message history could not load. Reopen the thread to try again.');
    });

    try {
      ws = new WebSocket(chatSocketUrl(API_BASE_URL, user.user_id, threadId));
      wsRef.current = ws;
      ws.pendingMessages = pendingMessages;
      ws.onopen = () => {
        if (!active) return;
        setWsStatus('connected');
        ping = setInterval(() => {
          if (active && ws.readyState === WebSocket.OPEN) {
            try { ws.send(JSON.stringify({ type: 'PING', timestamp: new Date().toISOString() })); } catch { setWsStatus('error'); }
          }
        }, 30000);
      };
      ws.onmessage = event => {
        if (!active) return;
        let data;
        try { data = JSON.parse(event.data); } catch {
          setError('A chat update could not be read. Reopen the thread to reconnect.');
          return;
        }
        switch (data.type) {
          case 'THREAD_CONNECTED':
            if (Array.isArray(data.history)) {
              socketHistory = true;
              setMessages(previous => [...data.history, ...previous.filter(message => pendingMessages.includes(messageId(message)))]);
            }
            break;
          case 'MESSAGE_SENT': {
            socketHistory = true;
            const pending = pendingMessages.shift();
            if (pending && data.message) setMessages(previous => previous.map(message => messageId(message) === pending ? data.message : message));
            break;
          }
          case 'ASSISTANT_TYPING': setTyping(true); break;
          case 'ASSISTANT_CHUNK':
            socketHistory = true;
            setMessages(previous => {
              const existing = previous.find(message => messageId(message) === data.message_id);
              return existing
                ? previous.map(message => messageId(message) === data.message_id ? { ...message, content: message.content + data.chunk } : message)
                : [...previous, { id: data.message_id, role: 'assistant', content: data.chunk, isPartial: true }];
            });
            break;
          case 'ASSISTANT_COMPLETE':
            socketHistory = true;
            setTyping(false);
            if (data.message) setMessages(previous => [...previous.filter(message => messageId(message) !== messageId(data.message)), data.message]);
            scheduleMetrics(threadId, 5000);
            break;
          case 'ERROR':
            setTyping(false);
            setError('The chat service could not complete this message. Try again.');
            break;
          default: break;
        }
      };
      ws.onclose = () => {
        clearInterval(ping);
        if (active) { setWsStatus('disconnected'); setTyping(false); }
      };
      ws.onerror = () => { if (active) setWsStatus('error'); };
    } catch {
      setWsStatus('error');
      setError('Live chat is unavailable. Messages can still use the HTTP API.');
    }
    return () => {
      active = false;
      selectionGenerationRef.current += 1;
      metricsRequestRef.current += 1;
      clearInterval(ping);
      for (const timer of timers) clearTimeout(timer);
      timers.clear();
      if (ws) ws.close();
      if (wsRef.current === ws) wsRef.current = null;
    };
  }, [selectedId, user.user_id, fetchThreadMetrics, scheduleMetrics]);

  const createThread = async () => {
    if (creatingRef.current) return;
    creatingRef.current = true;
    setCreatingThread(true);
    setError(null);
    try {
      const response = await axios.post(`${API_BASE_URL}/threads`, {
        user_id: user.user_id, title: `New Thread ${new Date().toLocaleString()}`, model_id: MODEL_ID
      });
      setThreads(previous => [response.data, ...previous.filter(thread => thread.thread_id !== response.data.thread_id)]);
      setCurrentThread(response.data);
    } catch { setError('The thread could not be created. Try again.'); }
    finally { creatingRef.current = false; setCreatingThread(false); }
  };

  const newMessage = drafts[selectedId] || '';
  const setNewMessage = value => setDrafts(previous => ({ ...previous, [selectedId]: value }));
  const clearSentDraft = (threadId, content) => setDrafts(previous => previous[threadId]?.trim() === content ? { ...previous, [threadId]: '' } : previous);
  const sendMessage = async () => {
    const content = newMessage.trim();
    const threadId = selectedId;
    const generation = selectionGenerationRef.current;
    const stillSelected = () => selectedIdRef.current === threadId && generation === selectionGenerationRef.current;
    if (!content || !threadId || sendingRef.current) return;
    const ws = wsRef.current;
    setError(null);
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: 'CHAT', message: content, model_id: MODEL_ID }));
        ws.historyAdvanced = true;
        const tempId = `temp-${++messageSequenceRef.current}`;
        ws.pendingMessages.push(tempId);
        setMessages(previous => [...previous, { id: tempId, role: 'user', content, timestamp: new Date().toISOString() }]);
        clearSentDraft(threadId, content);
        scheduleMetrics(threadId, 8000);
      } catch { setError('The message could not be sent. Your draft is still available.'); }
      return;
    }
    sendingRef.current = true;
    let sent = false;
    setLoading(true);
    try {
      await axios.post(`${API_BASE_URL}/messages`, { thread_id: threadId, user_id: user.user_id, content, role: 'user', model_id: MODEL_ID });
      sent = true;
      clearSentDraft(threadId, content);
      if (stillSelected()) {
        const response = await axios.get(`${API_BASE_URL}/messages/${threadId}/history`);
        if (stillSelected()) setMessages(response.data);
        scheduleMetrics(threadId, 5000);
      }
    } catch { if (stillSelected()) setError(sent ? 'Your message was sent, but history could not refresh. Reopen the thread to load it.' : 'The message could not be sent. Your draft is still available.'); }
    finally { sendingRef.current = false; setLoading(false); }
  };

  const handleTabChange = (_, value) => {
    setTabValue(value);
    if (value === 1 && selectedId) fetchThreadMetrics(selectedId, true);
  };
  const handleKeyPress = event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent?.isComposing && !loading) {
      event.preventDefault(); sendMessage();
    }
  };
  return { user, threads, currentThread, setCurrentThread, messages, newMessage, setNewMessage, loading,
    creatingThread, wsStatus, typing, loadingThreads, threadsError, error, clearError: () => setError(null),
    tabValue, threadMetrics, metricsError, metricsUpdatedAt, refreshingMetrics, fetchThreads, fetchThreadMetrics,
    createThread, sendMessage, handleTabChange, handleKeyPress };
}
