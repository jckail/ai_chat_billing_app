import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { WorkspaceView } from './App';
const workspace = () => ({ user: { username: 'testuser' }, threads: [{ thread_id: 1, title: 'Synthetic thread' }], currentThread: { thread_id: 1, title: 'Synthetic thread' }, messages: [], newMessage: '', wsStatus: 'disconnected', tabValue: 0,
  setCurrentThread: jest.fn(), setNewMessage: jest.fn(), createThread: jest.fn(), fetchThreads: jest.fn(), fetchThreadMetrics: jest.fn(), sendMessage: jest.fn(), handleTabChange: jest.fn(), handleKeyPress: jest.fn() });
test('workspace exposes named controls and linked panels without a dead invoice action', () => {
  render(<WorkspaceView workspace={workspace()} />);
  expect(screen.getByRole('textbox', { name: 'Message' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Refresh threads' })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'Chat' })).toHaveAttribute('aria-controls', 'chat-panel');
  expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', 'chat-tab');
  expect(screen.getByText('HTTP fallback')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /invoice/i })).not.toBeInTheDocument();
});
test('failed metrics offer an explicit retry rather than an endless spinner', () => {
  const state = { ...workspace(), tabValue: 1, metricsError: 'Usage metrics could not load. Try again.' };
  render(<WorkspaceView workspace={state} />);
  expect(screen.getByRole('alert')).toHaveTextContent('could not load');
  expect(screen.queryByLabelText('Loading billing metrics')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Retry metrics' }));
  expect(state.fetchThreadMetrics).toHaveBeenCalledWith(1, true);
});
