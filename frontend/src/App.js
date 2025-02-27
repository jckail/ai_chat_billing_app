import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Box, CssBaseline, Drawer, AppBar, Toolbar, Typography, Divider, 
         List, ListItem, ListItemButton, ListItemIcon, ListItemText, 
         Paper, TextField, Button, CircularProgress, Tabs, Tab, IconButton, Chip } from '@mui/material';
import { Add as AddIcon, Send as SendIcon, Refresh as RefreshIcon, 
         Forum as ForumIcon, Person as PersonIcon } from '@mui/icons-material';
import axios from 'axios';

// API base URL
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

// Default user (for POC, no auth required)
const DEFAULT_USER = {
  user_id: 1,
  username: 'testuser',
  email: 'test@example.com'
};

// Default model
const DEFAULT_MODEL = {
  model_id: 1,
  model_name: 'claude-3-5-haiku-20241022'
};

// Token pricing constants (per token)
const TOKEN_PRICING = {
  INPUT_PRICE: 0.000001, // $1 per million tokens
  OUTPUT_PRICE: 0.000005 // $5 per million tokens
};

function App() {
  // State
  const [user, setUser] = useState(null);
  const [threads, setThreads] = useState([]);
  const [currentThread, setCurrentThread] = useState(null);
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [wsStatus, setWsStatus] = useState('disconnected');
  const [typing, setTyping] = useState(false);
  
  // WebSocket reference
  const wsRef = useRef(null);
  const [loadingThreads, setLoadingThreads] = useState(false);
  const [tabValue, setTabValue] = useState(0);
  const [threadMetrics, setThreadMetrics] = useState(null);
  const [refreshingMetrics, setRefreshingMetrics] = useState(false);
  
  const drawerWidth = 280;

  // Function to establish WebSocket connection
  const connectWebSocket = useCallback((userId, threadId) => {
    if (!userId || !threadId) return null;
    
    // Close any existing connection
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.close();
    }
    
    // Create new WebSocket connection
    const wsUrl = `ws://localhost:8000/ws/chat/${userId}/${threadId}`;
    console.log(`Connecting to WebSocket: ${wsUrl}`);
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    
    // WebSocket event handlers
    ws.onopen = () => {
      console.log('WebSocket connected');
      setWsStatus('connected');
      
      // Start ping interval to keep connection alive
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: 'PING',
            timestamp: new Date().toISOString()
          }));
        } else {
          clearInterval(pingInterval);
        }
      }, 30000); // Send ping every 30 seconds
      
      // Store interval ID for cleanup
      ws.pingInterval = pingInterval;
    };
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('WebSocket message received:', data);
      
      switch (data.type) {
        case 'THREAD_CONNECTED':
          // Handle initial thread connection with history
          if (data.history && Array.isArray(data.history)) {
            setMessages(data.history);
          }
          break;
          
        case 'MESSAGE_SENT':
          // Confirmation of user message received by server
          break;
          
        case 'ASSISTANT_TYPING':
          // AI is generating a response
          setTyping(true);
          break;
          
        case 'ASSISTANT_CHUNK':
          // Incremental AI response chunk
          setMessages(prevMessages => {
            // Find if we already have a partial message
            const existingIndex = prevMessages.findIndex(m => 
              m.id === data.message_id || m.messageId === data.message_id);
            
            if (existingIndex >= 0) {
              // Update existing message
              const updatedMessages = [...prevMessages];
              updatedMessages[existingIndex] = {
                ...updatedMessages[existingIndex],
                content: updatedMessages[existingIndex].content + data.chunk
              };
              return updatedMessages;
            } else {
              // Add new partial message
              return [...prevMessages, {
                id: data.message_id,
                messageId: data.message_id,
                role: 'assistant',
                content: data.chunk,
                isPartial: true
              }];
            }
          });
          break;
          
        case 'ASSISTANT_COMPLETE':
          // Final complete AI response
          setTyping(false);
          setMessages(prevMessages => {
            // Replace partial message with complete one if it exists
            const updatedMessages = prevMessages.filter(m => m.id !== data.message.id);
            return [...updatedMessages, data.message];
          });
          
          // Update metrics
          if (currentThread) {
            // Add a small delay to ensure backend has processed token metrics
            setTimeout(() => {
              // Use refresh=true to force a fresh calculation
              setRefreshingMetrics(true);
              fetchThreadMetrics(currentThread.thread_id, true)
                .then(() => setRefreshingMetrics(false))
                .catch(err => console.error("[BILLING] Error refreshing metrics:", err));
              console.log("[BILLING] Fetching updated thread metrics after message completion (with refresh)");
            }, 5000); // 5 second delay to ensure backend processing completes
          }
          break;
          
        case 'PONG':
          // Received pong (connection is alive)
          break;
          
        case 'ERROR':
          console.error('WebSocket error:', data.error);
          break;
          
        default:
          console.log('Unknown message type:', data.type);
      }
    };
    
    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setWsStatus('disconnected');
      
      if (ws.pingInterval) {
        clearInterval(ws.pingInterval);
      }
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setWsStatus('error');
    };
    
    return ws;
  }, []);

  // Initialize the app
  useEffect(() => {
    // For POC, we'll just use the default user
    setUser(DEFAULT_USER);
    
    // Load threads for the default user
    fetchThreads(DEFAULT_USER.user_id);
    
    // Cleanup WebSocket on unmount
    return () => {
      if (wsRef.current) {
        if (wsRef.current.pingInterval) {
          clearInterval(wsRef.current.pingInterval);
        }
        wsRef.current.close();
      }
    };
  }, []);

  // Fetch user threads on component mount
  useEffect(() => {
    if (user) {
      fetchThreads(user.user_id);
    }
  }, [user]);

  // Connect to WebSocket when current thread changes
  useEffect(() => {
    if (currentThread && user) {
      fetchMessages(currentThread.thread_id);
      fetchThreadMetrics(currentThread.thread_id);
      
      // Connect to WebSocket for this thread
      connectWebSocket(user.user_id, currentThread.thread_id);
    }
    
    // Cleanup function that runs when the component unmounts or when dependencies change
    return () => {
      // Safely close any WebSocket connection
      if (wsRef.current) {
        if (wsRef.current.pingInterval) {
          clearInterval(wsRef.current.pingInterval);
        }
        wsRef.current.close();
      }
    };
  }, [currentThread, connectWebSocket, user]);

  // Scroll messages into view when they change
  useEffect(() => {
    const messagesContainer = document.querySelector('.message-container');
    if (messagesContainer) {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
  }, [messages]);

  // Fetch user's threads
  const fetchThreads = async (userId) => {
    setLoadingThreads(true);
    try {
      const response = await axios.get(`${API_BASE_URL}/threads?user_id=${userId}`);
      setThreads(response.data);
      
      // If there are threads and no current thread, set the first thread as current
      if (response.data.length > 0 && !currentThread) {
        setCurrentThread(response.data[0]);
      }
    } catch (error) {
      console.error('Error fetching threads:', error);
    } finally {
      setLoadingThreads(false);
    }
  };

  // Send a message via WebSocket
  const sendMessageWs = async () => {
    if (!newMessage.trim() || !currentThread) return;
    
    const messageContent = newMessage.trim();
    setNewMessage('');
    
    // Add user message to the UI immediately
    const tempUserMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: messageContent,
      timestamp: new Date().toISOString()
    };
    setMessages(prevMessages => [...prevMessages, tempUserMessage]);
    
    // Send message through WebSocket if connected
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'CHAT',
        message: messageContent,
        model_id: DEFAULT_MODEL.model_id
      }));
      
      // Schedule metrics update
      setTimeout(() => {
        console.log("[BILLING] Fetching metrics after WebSocket message send");
        setRefreshingMetrics(true);
        fetchThreadMetricsWithRetry(currentThread.thread_id, true, 0)
          .then(() => setRefreshingMetrics(false));
      }, 8000); // Increased from 5 to 8 seconds to ensure backend has time to process
    }
  };

  // Fetch messages for a thread
  const fetchMessages = async (threadId) => {
    // Only fetch if we're not using WebSockets yet
    if (wsStatus === 'connected') {
      console.log('Using WebSocket connection for messages');
      return;
    }
    
    // Otherwise fall back to REST API
    console.log('Falling back to REST API for messages');
    
    try {
      const response = await axios.get(`${API_BASE_URL}/messages/${threadId}/history`);
      setMessages(response.data);
    } catch (error) {
      console.error('Error fetching messages:', error);
    }
  };
  
  // Fetch thread metrics
  const fetchThreadMetrics = async (threadId, refresh = false) => {
    return fetchThreadMetricsWithRetry(threadId, refresh, 0);
  };
  
  // Helper function with retry logic
  const fetchThreadMetricsWithRetry = async (threadId, refresh = false, retryCount = 0) => {
    const url = `${API_BASE_URL}/billing/metrics/thread/${threadId}${refresh ? '?refresh=true' : ''}`;
    console.log(`[BILLING] Fetching metrics from: ${url}`);
    try {
      const response = await axios.get(url);
      console.log("[BILLING] Thread metrics received:", response.data, refresh ? "(fresh calculation)" : "(from cache)");
      
      // Check if metrics show zero tokens but we have messages
      if (response.data.total_input_tokens === 0 && 
          response.data.total_output_tokens === 0 && 
          response.data.total_messages > 0 && 
          retryCount < 3) {
        
        console.log(`[BILLING] Metrics show zero tokens but thread has ${response.data.total_messages} messages. Retrying...`);
        // Wait and retry with a forced refresh
        await new Promise(resolve => setTimeout(resolve, 3000));
        return fetchThreadMetricsWithRetry(threadId, true, retryCount + 1);
      }
      
      setThreadMetrics(response.data);
      return response.data;
    } catch (error) {
      console.error('[BILLING] Error fetching thread metrics:', error);
      
      // On error, retry if we haven't tried too many times
      if (retryCount < 3) {
        console.log(`[BILLING] Retrying metrics fetch (attempt ${retryCount + 1}/3)`);
        await new Promise(resolve => setTimeout(resolve, 2000));
        return fetchThreadMetricsWithRetry(threadId, refresh, retryCount + 1);
      }
      
      return null;
    }
  };

  // Create a new thread
  const createThread = async () => {
    try {
      const response = await axios.post(`${API_BASE_URL}/threads`, {
        user_id: user.user_id,
        title: `New Thread ${new Date().toLocaleString()}`,
        model_id: DEFAULT_MODEL.model_id
      });
      
      // Update threads list and set the new thread as current
      fetchThreads(user.user_id);
      setCurrentThread(response.data);
    } catch (error) {
      console.error('Error creating thread:', error);
    }
  };

  // Send a message
  const sendMessage = async () => {
    if (!newMessage.trim() || !currentThread) return;

    // Try to use WebSocket if available
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      sendMessageWs();
      return;
    }
    
    // Fall back to REST API if WebSocket is not available
    console.log('Using REST API for sending message');
    setLoading(true);
    try {
      const response = await axios.post(`${API_BASE_URL}/messages`, {
        thread_id: currentThread.thread_id,
        user_id: user.user_id,
        content: newMessage,
        role: 'user',
        model_id: DEFAULT_MODEL.model_id
      });
      
      // Clear the input and refresh messages
      setNewMessage('');
      fetchMessages(currentThread.thread_id);
      
      // Schedule metrics update with a delay to allow processing
      setTimeout(() => {
        console.log("[BILLING] Fetching metrics after REST API message send");
        setRefreshingMetrics(true);
        fetchThreadMetrics(currentThread.thread_id, true)
          .then(() => setRefreshingMetrics(false));
      }, 5000);
    } catch (error) {
      console.error('Error sending message:', error);
    } finally {
      setLoading(false);
    }
  };

  // Handle tab change
  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
    // Refresh metrics when switching to the billing tab
    if (newValue === 1 && currentThread) {
      console.log("[BILLING] Tab changed to billing details, refreshing metrics");
      setRefreshingMetrics(true);
      // Use the retry version for more reliability
      fetchThreadMetricsWithRetry(currentThread.thread_id, true, 0)
        .then(() => setRefreshingMetrics(false))
        .catch(err => {
          console.error("[BILLING] Error refreshing metrics:", err);
          setRefreshingMetrics(false);
        });
    }
  };

  // Handle sending message with Enter key
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !loading) {
      e.preventDefault();
      sendMessage();
    }
  };

  // Helper to format numbers
  const formatNumber = (num) => {
    return num.toLocaleString();
  };

  // Format currency
  const formatCurrency = (amount) => {
    return `$${parseFloat(amount).toFixed(6)}`;
  };

  return (
    <Box sx={{ display: 'flex' }}>
      <CssBaseline />
      
      {/* App Bar */}
      <AppBar
        position="fixed"
        sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}
      >
        <Toolbar sx={{ display: 'flex', alignItems: 'center' }}>
          <Box sx={{ mr: 2, fontSize: '1.2rem' }}>{wsStatus === 'connected' ? '🟢' : '🔴'}</Box>
          <Typography variant="h6" noWrap component="div">
            AI Thread Billing
          </Typography>
        </Toolbar>
      </AppBar>
      
      {/* Side Drawer - Thread List */}
      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          [`& .MuiDrawer-paper`]: { width: drawerWidth, boxSizing: 'border-box' },
        }}
      >
        <Toolbar />
        <Box sx={{ overflow: 'auto', p: 2 }}>
          {/* User Info */}
          {user && (
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <PersonIcon sx={{ mr: 1 }} />
                <Typography variant="subtitle1">{user.username}</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary">
                {user.email}
              </Typography>
            </Box>
          )}
          
          <Divider sx={{ my: 2 }} />
          
          {/* Create Thread Button */}
          <Button 
            variant="contained" 
            startIcon={<AddIcon />}
            fullWidth
            onClick={createThread}
            sx={{ mb: 2 }}
          >
            New Thread
          </Button>
          
          {/* Thread List */}
          <Typography variant="subtitle1" sx={{ mt: 2, mb: 1 }}>
            Your Threads
            <IconButton size="small" onClick={() => user && fetchThreads(user.user_id)} sx={{ ml: 1 }}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Typography>
          
          {loadingThreads ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', my: 3 }}>
              <CircularProgress size={24} />
            </Box>
          ) : (
            <List>
              {threads.map((thread) => (
                <ListItem key={thread.thread_id} disablePadding>
                  <ListItemButton 
                    selected={currentThread && currentThread.thread_id === thread.thread_id}
                    onClick={() => setCurrentThread(thread)}
                  >
                    <ListItemIcon>
                      <ForumIcon />
                    </ListItemIcon>
                    <ListItemText 
                      primary={thread.title} 
                      secondary={new Date(thread.updated_at).toLocaleString()}
                    />
                  </ListItemButton>
                </ListItem>
              ))}
              {threads.length === 0 && (
                <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
                  No threads yet. Create one to get started.
                </Typography>
              )}
            </List>
          )}
        </Box>
      </Drawer>
      
      {/* Main Content */}
      <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
        <Toolbar />
        
        {currentThread ? (
          <>
            {/* Thread Title and Metrics */}
            <Paper sx={{ p: 2, mb: 2 }}>
              <Typography variant="h6">{currentThread.title}</Typography>
              <Typography variant="body2" color="text.secondary">
                Created: {new Date(currentThread.created_at).toLocaleString()}
              </Typography>
              
              {threadMetrics && (
                <Box sx={{ mt: 2, display: 'flex', gap: 3 }}>
                  <Box>
                    <Typography variant="body2" color="text.secondary">Messages</Typography>
                    <Typography variant="h6">{threadMetrics.total_messages}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="text.secondary">Input Tokens</Typography>
                    <Typography variant="h6">{threadMetrics.total_input_tokens}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="text.secondary">Output Tokens</Typography>
                    <Typography variant="h6">{threadMetrics.total_output_tokens}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="text.secondary">Total Cost</Typography>
                    <Typography variant="h6" color="primary">
                      {formatCurrency(threadMetrics.total_cost)}
                    </Typography>
                  </Box>
                </Box>
              )}
            </Paper>
            
            {/* Tabs for Chat/Billing */}
            <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
              <Tabs value={tabValue} onChange={handleTabChange}>
                <Tab label="Chat" />
                <Tab label="Billing Details" />
              </Tabs>
            </Box>
            
            {/* Chat Tab */}
            {tabValue === 0 && (
              <>
                {/* Messages */}
                <Paper className="message-container">
                  {messages.length === 0 ? (
                    <Typography variant="body1" sx={{ p: 2, textAlign: 'center' }}>
                      No messages yet. Start the conversation!
                    </Typography>
                  ) : (
                    <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                      {messages.map((message) => (
                        <Box
                          key={message.id || message.message_id}
                          className={`message ${message.role === 'user' ? 'user-message' : 'assistant-message'}`}
                        >
                          <Typography variant="body1">
                            {message.content}
                          </Typography>
                          <Box className="message-info">
                            <Typography variant="caption">
                              {message.timestamp ? new Date(message.timestamp).toLocaleTimeString() : 
                               message.created_at ? new Date(message.created_at).toLocaleTimeString() : 
                               new Date().toLocaleTimeString()}
                            </Typography>
                            <Box className="token-info">
                              <Typography variant="caption">
                                Role: {message.role}
                              </Typography>
                              {(message.token_count || message.input_tokens || message.output_tokens) && (
                                <Typography variant="caption" className="cost-badge">
                                  Cost: {formatCurrency(
                                    message.role === 'user' 
                                      ? ((message.token_count || message.input_tokens || 0) * TOKEN_PRICING.INPUT_PRICE) 
                                      : ((message.token_count || message.output_tokens || 0) * TOKEN_PRICING.OUTPUT_PRICE)
                                  )}
                                  <Chip 
                                    size="small" 
                                    label={message.role === 'user' 
                                      ? `${message.token_count || message.input_tokens || 0} input tokens` 
                                      : `${message.token_count || message.output_tokens || 0} output tokens`
                                    }
                                    variant="outlined"
                                    sx={{ ml: 1, fontSize: '0.7rem' }}
                                  />
                                </Typography>
                              )}
                            </Box>
                          </Box>
                        </Box>
                      ))}
                      
                      {typing && <Box sx={{ p: 2, fontStyle: 'italic', color: 'text.secondary' }}>Claude is typing...</Box>}
                    </Box>
                  )}
                </Paper>
                
                {/* Message Input */}
                <Paper sx={{ p: 2, mt: 2 }}>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <TextField
                      fullWidth
                      variant="outlined"
                      placeholder="Type your message here..."
                      value={newMessage}
                      onChange={(e) => setNewMessage(e.target.value)}
                      onKeyDown={handleKeyPress}
                      disabled={loading}
                    />
                    <Button
                      variant="contained"
                      endIcon={loading ? <CircularProgress size={20} /> : <SendIcon />}
                      onClick={sendMessage}
                      disabled={loading || !newMessage.trim()}
                    >
                      Send
                    </Button>
                  </Box>
                </Paper>
              </>
            )}
            
            {/* Billing Tab */}
            {tabValue === 1 && (
              <Paper sx={{ p: 3 }}>
                <Typography variant="h6" gutterBottom>
                  Billing Details
                </Typography>
                
                {threadMetrics ? (
                  <>
                    <Box sx={{ mb: 3 }}>
                      <Typography variant="subtitle1">Thread Metrics</Typography>
                      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 2, mt: 1 }}>
                        <Paper sx={{ p: 2 }}>
                          <Typography variant="body2" color="text.secondary">Total Messages</Typography>
                          <Typography variant="h6">{threadMetrics.total_messages}</Typography>
                        </Paper>
                        <Paper sx={{ p: 2 }}>
                          <Typography variant="body2" color="text.secondary">Last Activity</Typography>
                          <Typography variant="h6">
                            {new Date(threadMetrics.last_activity).toLocaleString()}
                          </Typography>
                        </Paper>
                        <Paper sx={{ p: 2 }}>
                          <Typography variant="body2" color="text.secondary">Input Tokens</Typography>
                          <Typography variant="h6">{threadMetrics.total_input_tokens}</Typography>
                        </Paper>
                        <Paper sx={{ p: 2 }}>
                          <Typography variant="body2" color="text.secondary">Output Tokens</Typography>
                          <Typography variant="h6">{threadMetrics.total_output_tokens}</Typography>
                        </Paper>
                      </Box>
                      <Box sx={{ mt: 2, display: 'flex', justifyContent: 'flex-end' }}>
                        <Button 
                          onClick={() => {
                            setRefreshingMetrics(true);
                            // Use the retry version with force refresh
                            fetchThreadMetricsWithRetry(currentThread.thread_id, true, 0)
                              .then(() => setRefreshingMetrics(false))
                              .catch(() => setRefreshingMetrics(false));
                          }}
                          startIcon={refreshingMetrics ? <CircularProgress size={16} /> : <RefreshIcon />} 
                          size="small"
                          disabled={refreshingMetrics}
                        >
                          {refreshingMetrics ? 'Refreshing...' : 'Refresh Metrics'}
                        </Button>
                      </Box>
                    </Box>
                    
                    <Box sx={{ mt: 4 }}>
                      <Typography variant="subtitle1" gutterBottom>
                        Cost Breakdown
                      </Typography>
                      <Paper sx={{ p: 2, mb: 2, bgcolor: '#f9f9f9' }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                          <Typography variant="body2">Input Tokens ({threadMetrics.total_input_tokens})</Typography>
                          <Typography variant="body2">
                            {formatCurrency(threadMetrics.total_input_tokens * TOKEN_PRICING.INPUT_PRICE)}
                          </Typography>
                        </Box>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                          <Typography variant="body2">Output Tokens ({threadMetrics.total_output_tokens})</Typography>
                          <Typography variant="body2">
                            {formatCurrency(threadMetrics.total_output_tokens * TOKEN_PRICING.OUTPUT_PRICE)}
                          </Typography>
                        </Box>
                        <Divider sx={{ my: 1 }} />
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                          <Typography variant="subtitle2">Total Cost</Typography>
                          <Typography variant="subtitle2" color="primary">
                            {formatCurrency(threadMetrics.total_cost)}
                          </Typography>
                        </Box>
                        
                        {/* Debug Information Box */}
                        <Box sx={{ mt: 2, p: 2, bgcolor: '#f5f5f5', borderRadius: 1, fontSize: '0.8rem' }}>
                          <Typography variant="subtitle2" gutterBottom>Debug Information:</Typography>
                          <Typography variant="caption" component="div">
                            Last metrics update: {new Date().toLocaleTimeString()}
                          </Typography>
                          <Typography variant="caption" component="div">
                            Messages: {threadMetrics.total_messages}
                          </Typography>
                          <Typography variant="caption" component="div">
                            Raw cost calculation: ({threadMetrics.total_input_tokens} × ${TOKEN_PRICING.INPUT_PRICE}) + 
                            ({threadMetrics.total_output_tokens} × ${TOKEN_PRICING.OUTPUT_PRICE}) = ${formatCurrency(threadMetrics.total_cost)}
                          </Typography>
                        </Box>
                      </Paper>
                      
                      <Button variant="outlined" sx={{ mt: 2 }}>
                        Generate Invoice
                      </Button>
                    </Box>
                  </>
                ) : (
                  <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
                    <CircularProgress />
                  </Box>
                )}
              </Paper>
            )}
          </>
        ) : (
          <Paper sx={{ p: 4, textAlign: 'center' }}>
            <Typography variant="h6" gutterBottom>
              Welcome to AI Thread Billing
            </Typography>
            <Typography variant="body1" paragraph>
              Select a thread from the sidebar or create a new one to start chatting.
            </Typography>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={createThread}
              sx={{ mt: 2 }}
            >
              Create New Thread
            </Button>
          </Paper>
        )}
      </Box>
    </Box>
  );
}

export default App;