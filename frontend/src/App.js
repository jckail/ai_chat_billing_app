import React, { useEffect, useRef } from 'react';
import { Box, CssBaseline, Drawer, AppBar, Toolbar, Typography, Divider,
  List, ListItemButton, ListItemText, Paper, TextField, Button, CircularProgress,
  Tabs, Tab, IconButton, Chip, Alert } from '@mui/material';
import { Add, Send, Refresh } from '@mui/icons-material';
import useWorkspace from './useWorkspace';
import { formatCurrency, messageId, tokenCount } from './endpoints';

function dateLabel(value) {
  if (!value) return 'Not available';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not available' : date.toLocaleString();
}

export function WorkspaceView({ workspace }) {
  const { user, threads, currentThread, setCurrentThread, messages, newMessage, setNewMessage, loading,
    creatingThread, wsStatus, typing, loadingThreads, threadsError, error, clearError, tabValue,
    threadMetrics, metricsError, metricsUpdatedAt, refreshingMetrics, fetchThreads, fetchThreadMetrics,
    createThread, sendMessage, handleTabChange, handleKeyPress } = workspace;
  const messageContainer = useRef(null);
  useEffect(() => {
    if (messageContainer.current) messageContainer.current.scrollTop = messageContainer.current.scrollHeight;
  }, [messages, typing]);
  const createButton = <Button startIcon={<Add />} variant="contained" onClick={createThread}
    disabled={creatingThread}>{creatingThread ? 'Creating…' : 'New thread'}</Button>;
  const status = wsStatus === 'connected' ? 'Live chat connected' : wsStatus === 'connecting' ? 'Connecting…' : 'HTTP fallback';
  return <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, minHeight: '100vh' }}>
    <CssBaseline />
    <AppBar position="fixed" sx={{ zIndex: theme => theme.zIndex.drawer + 1 }}>
      <Toolbar sx={{ gap: 1 }}>
        <Typography component="h1" variant="h6" sx={{ flexGrow: 1, minWidth: 0, fontSize: { xs: '1rem', sm: '1.25rem' } }}>AI Thread Billing</Typography>
        <Chip label={status} size="small" sx={{ flexShrink: 0, fontSize: { xs: '0.65rem', sm: '0.8125rem' } }} color={wsStatus === 'connected' ? 'success' : 'default'} />
      </Toolbar>
    </AppBar>
    <Drawer variant="permanent" sx={{ width: { xs: '100%', md: 280 }, flexShrink: 0,
      '& .MuiDrawer-paper': { width: { xs: '100%', md: 280 }, position: { xs: 'relative', md: 'fixed' }, boxSizing: 'border-box' } }}>
      <Toolbar />
      <Box component="nav" aria-label="Conversation threads" sx={{ p: 2 }}>
        <Typography variant="subtitle1">{user.username}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Demo account · no authentication</Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          {createButton}<IconButton aria-label="Refresh threads" onClick={fetchThreads} disabled={loadingThreads}><Refresh /></IconButton>
        </Box>
        {threadsError && <Alert severity="error" sx={{ mt: 2 }}>{threadsError}<Button onClick={fetchThreads}>Retry</Button></Alert>}
        {loadingThreads && <Box sx={{ p: 2 }}><CircularProgress size={24} aria-label="Loading threads" /></Box>}
        <List sx={{ maxHeight: { xs: 240, md: 'none' }, overflowY: 'auto' }}>
          {threads.map(thread => <ListItemButton key={thread.thread_id} selected={thread.thread_id === currentThread?.thread_id}
            aria-current={thread.thread_id === currentThread?.thread_id ? 'true' : undefined} onClick={() => setCurrentThread(thread)}>
            <ListItemText primary={thread.title} secondary={dateLabel(thread.created_at)} primaryTypographyProps={{ sx: { overflowWrap: 'anywhere' } }} />
          </ListItemButton>)}
        </List>
        {!loadingThreads && !threadsError && threads.length === 0 && <Typography color="text.secondary">No threads yet.</Typography>}
      </Box>
    </Drawer>
    <Box component="main" sx={{ flexGrow: 1, minWidth: 0, p: { xs: 2, sm: 3 } }}>
      <Toolbar sx={{ display: { xs: 'none', md: 'flex' } }} />
      {error && <Alert severity="error" onClose={clearError} sx={{ mb: 2 }}>{error}</Alert>}
      {currentThread ? <>
        <Typography component="h2" variant="h5" sx={{ overflowWrap: 'anywhere', mb: 1 }}>{currentThread.title}</Typography>
        <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>Chat and review this thread’s reported usage.</Typography>
        <Tabs value={tabValue} onChange={handleTabChange} aria-label="Thread workspace">
          <Tab label="Chat" id="chat-tab" aria-controls="chat-panel" />
          <Tab label="Billing details" id="billing-tab" aria-controls="billing-panel" />
        </Tabs>
        <Box role="tabpanel" id="chat-panel" aria-labelledby="chat-tab" hidden={tabValue !== 0} sx={{ pt: 2 }}>
          <Paper ref={messageContainer} role="region" aria-label="Conversation messages" tabIndex={0}
            sx={{ p: 2, height: { xs: 360, md: '55vh' }, overflowY: 'auto', mb: 2 }}>
            {messages.length === 0 && <Typography color="text.secondary">Start the conversation with a message.</Typography>}
            {messages.map((message, index) => <Box key={messageId(message) ?? index} sx={{ mb: 2, display: 'flex', justifyContent: message.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <Box sx={{ p: 2, borderRadius: 2, maxWidth: { xs: '100%', sm: '85%' }, minWidth: 0,
                bgcolor: message.role === 'user' ? 'primary.main' : 'grey.100', color: message.role === 'user' ? 'primary.contrastText' : 'text.primary' }}>
                <Typography variant="subtitle2">{message.role === 'user' ? 'You' : 'Assistant'}</Typography>
                <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{message.content}</Typography>
                <Typography variant="caption" component="p" sx={{ mt: 1 }}>{dateLabel(message.created_at || message.timestamp)}</Typography>
                {tokenCount(message) != null && <Typography variant="caption">{tokenCount(message)} tokens</Typography>}
                {message.total_cost != null && <Typography variant="caption" sx={{ ml: 1 }}>{formatCurrency(message.total_cost)}</Typography>}
              </Box>
            </Box>)}
            {typing && <Typography role="status" color="text.secondary">Assistant is typing…</Typography>}
          </Paper>
          <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 1 }}>
            <TextField fullWidth multiline maxRows={6} label="Message" value={newMessage} onChange={event => setNewMessage(event.target.value)}
              onKeyDown={handleKeyPress} disabled={loading} helperText="Enter to send · Shift+Enter for a new line" />
            <Button variant="contained" onClick={sendMessage} disabled={loading || !newMessage.trim()} startIcon={<Send />} sx={{ mb: 3 }}>{loading ? 'Sending…' : 'Send'}</Button>
          </Box>
        </Box>
        <Box role="tabpanel" id="billing-panel" aria-labelledby="billing-tab" hidden={tabValue !== 1} sx={{ pt: 2 }}>
          <Paper sx={{ p: { xs: 2, sm: 3 } }}>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
              <Typography component="h3" variant="h6">Thread usage</Typography>
              <Button startIcon={<Refresh />} disabled={refreshingMetrics} onClick={() => fetchThreadMetrics(currentThread.thread_id, true)}>{refreshingMetrics ? 'Refreshing…' : 'Refresh metrics'}</Button>
            </Box>
            {metricsError && <Alert severity="error" sx={{ mb: 2 }}>{metricsError}<Button onClick={() => fetchThreadMetrics(currentThread.thread_id, true)}>Retry metrics</Button></Alert>}
            {!threadMetrics && !metricsError && <CircularProgress size={24} aria-label="Loading billing metrics" />}
            {threadMetrics && <>
              <Box component="dl" sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 3 }}>
                {[['Messages', threadMetrics.total_messages], ['Input tokens', threadMetrics.total_input_tokens], ['Output tokens', threadMetrics.total_output_tokens], ['Reported total cost', formatCurrency(threadMetrics.total_cost)]].map(([label, value]) => <Box key={label}>
                  <Typography component="dt" color="text.secondary">{label}</Typography><Typography component="dd" variant="h5" sx={{ m: 0 }}>{value ?? 'Not available'}</Typography>
                </Box>)}
              </Box>
              <Divider sx={{ my: 2 }} />
              <Typography variant="body2" color="text.secondary">Costs reflect the backend’s configured rates. Usage may update after message processing finishes.</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>Last activity: {dateLabel(threadMetrics.last_activity)}</Typography>
              <Typography variant="body2" color="text.secondary">Metrics retrieved: {dateLabel(metricsUpdatedAt)}</Typography>
            </>}
            <Typography variant="body2" color="text.secondary" sx={{ mt: 3 }}>Invoice generation is unavailable in this interface.</Typography>
          </Paper>
        </Box>
      </> : <Paper sx={{ p: 3 }}><Typography component="h2" variant="h5" sx={{ mb: 1 }}>Your conversation workspace</Typography>
        <Typography sx={{ mb: 3 }}>Create a thread to start chatting and reviewing usage.</Typography>{createButton}</Paper>}
    </Box>
  </Box>;
}

export default function App() { return <WorkspaceView workspace={useWorkspace()} />; }
