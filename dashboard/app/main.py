import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import sqlite3
import redis
import json
import os
import time
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

# Environment variables
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/billing.db")
REFRESH_INTERVAL = 15  # Refresh interval in seconds

# Parse SQLite database path
if DATABASE_URL.startswith("sqlite:///"):
    DB_PATH = DATABASE_URL[10:]
else:
    DB_PATH = ":memory:"

# Setup page config
st.set_page_config(
    page_title="AI Thread Billing Dashboard",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Redis connection
@st.cache_resource
def get_redis_connection():
    try:
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        # Test the connection
        r.ping()
        return r
    except Exception as e:
        st.error(f"Failed to connect to Redis: {e}")
        return None

# SQLite connection
@st.cache_resource
def get_db_connection():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        return None

# Function to get data from Redis
def get_redis_data(redis_conn, prefix, key_type, key_id=None):
    try:
        if key_id is None:
            # Get pattern matching keys
            pattern = f"{prefix}{key_type}:*"
            keys = redis_conn.keys(pattern)
            result = []
            for key in keys:
                value = redis_conn.get(key)
                if value:
                    try:
                        result.append(json.loads(value))
                    except:
                        pass  # Ignore non-JSON values
            return result
        else:
            # Get specific key
            key = f"{prefix}{key_type}:{key_id}"
            value = redis_conn.get(key)
            if value:
                try:
                    return json.loads(value)
                except:
                    return None
            return None
    except Exception as e:
        st.error(f"Redis error: {e}")
        return None

# Function to query SQLite database
def query_db(conn, query, params=()):
    try:
        df = pd.read_sql_query(query, conn, params=params)
        return df
    except Exception as e:
        st.error(f"Database error: {e}")
        return pd.DataFrame()

# Get real-time user metrics
def get_user_metrics(redis_conn, db_conn, user_id=None):
    # Try Redis first for real-time data
    if redis_conn:
        if user_id:
            metrics = get_redis_data(redis_conn, "billing:", "user_metrics", user_id)
        else:
            metrics = get_redis_data(redis_conn, "billing:", "user_metrics")
            # Flatten the list of lists
            if metrics:
                metrics = [item for sublist in metrics for item in sublist]
        
        if metrics:
            return pd.DataFrame(metrics)
    
    # Fall back to SQLite for historical data
    if db_conn:
        if user_id:
            query = """
            SELECT
                u.username,
                t.thread_id,
                t.title as thread_title,
                COUNT(m.message_id) as total_messages,
                SUM(CASE WHEN mt.token_type = 'input' THEN mt.token_count ELSE 0 END) as total_input_tokens,
                SUM(CASE WHEN mt.token_type = 'output' THEN mt.token_count ELSE 0 END) as total_output_tokens,
                MAX(m.created_at) as last_activity
            FROM
                user_threads t
                JOIN user_thread_messages m ON t.thread_id = m.thread_id
                JOIN message_tokens mt ON m.message_id = mt.message_id
                JOIN dim_users u ON t.user_id = u.user_id
            WHERE
                t.user_id = ?
            GROUP BY
                t.thread_id
            """
            df = query_db(db_conn, query, (user_id,))
        else:
            query = """
            SELECT
                u.user_id,
                u.username,
                COUNT(DISTINCT t.thread_id) as thread_count,
                COUNT(m.message_id) as total_messages,
                SUM(CASE WHEN mt.token_type = 'input' THEN mt.token_count ELSE 0 END) as total_input_tokens,
                SUM(CASE WHEN mt.token_type = 'output' THEN mt.token_count ELSE 0 END) as total_output_tokens,
                MAX(m.created_at) as last_activity
            FROM
                dim_users u
                LEFT JOIN user_threads t ON u.user_id = t.user_id
                LEFT JOIN user_thread_messages m ON t.thread_id = m.thread_id
                LEFT JOIN message_tokens mt ON m.message_id = mt.message_id
            GROUP BY
                u.user_id
            """
            df = query_db(db_conn, query)
        
        return df
    
    return pd.DataFrame()

# Get thread metrics
def get_thread_metrics(redis_conn, db_conn, thread_id=None):
    # Try Redis first
    if redis_conn:
        if thread_id:
            metrics = get_redis_data(redis_conn, "billing:", "thread_metrics", thread_id)
            if metrics:
                return pd.DataFrame([metrics])
        else:
            metrics = get_redis_data(redis_conn, "billing:", "thread_metrics")
            if metrics:
                return pd.DataFrame(metrics)
    
    # Fall back to SQLite
    if db_conn:
        if thread_id:
            query = """
            SELECT
                t.thread_id,
                t.title as thread_title,
                u.username,
                COUNT(m.message_id) as total_messages,
                SUM(CASE WHEN mt.token_type = 'input' THEN mt.token_count ELSE 0 END) as total_input_tokens,
                SUM(CASE WHEN mt.token_type = 'output' THEN mt.token_count ELSE 0 END) as total_output_tokens,
                MAX(m.created_at) as last_activity
            FROM
                user_threads t
                JOIN user_thread_messages m ON t.thread_id = m.thread_id
                JOIN message_tokens mt ON m.message_id = mt.message_id
                JOIN dim_users u ON t.user_id = u.user_id
            WHERE
                t.thread_id = ?
            GROUP BY
                t.thread_id
            """
            df = query_db(db_conn, query, (thread_id,))
        else:
            query = """
            SELECT
                t.thread_id,
                t.title as thread_title,
                u.username,
                COUNT(m.message_id) as total_messages,
                SUM(CASE WHEN mt.token_type = 'input' THEN mt.token_count ELSE 0 END) as total_input_tokens,
                SUM(CASE WHEN mt.token_type = 'output' THEN mt.token_count ELSE 0 END) as total_output_tokens,
                MAX(m.created_at) as last_activity
            FROM
                user_threads t
                JOIN user_thread_messages m ON t.thread_id = m.thread_id
                JOIN message_tokens mt ON m.message_id = mt.message_id
                JOIN dim_users u ON t.user_id = u.user_id
            GROUP BY
                t.thread_id
            """
            df = query_db(db_conn, query)
        
        return df
    
    return pd.DataFrame()

# Get token pricing data
def get_token_pricing(db_conn):
    query = """
    SELECT
        m.model_name,
        tp.input_token_price,
        tp.output_token_price,
        tp.effective_from,
        tp.is_current
    FROM
        dim_token_pricing tp
        JOIN dim_models m ON tp.model_id = m.model_id
    ORDER BY
        m.model_name, tp.effective_from DESC
    """
    return query_db(db_conn, query)

# Calculate costs from token counts
def calculate_costs(df, pricing_df):
    if pricing_df.empty or df.empty:
        return df
    
    # Get current pricing
    current_pricing = pricing_df[pricing_df['is_current'] == 1]
    if current_pricing.empty:
        # Use default pricing
        input_price = 0.00000025  # $0.25 per million tokens
        output_price = 0.00000075  # $0.75 per million tokens
    else:
        # Use first current pricing (assuming one model for simplicity)
        input_price = current_pricing.iloc[0]['input_token_price']
        output_price = current_pricing.iloc[0]['output_token_price']
    
    # Calculate costs
    if 'total_input_tokens' in df.columns and 'total_output_tokens' in df.columns:
        df['input_cost'] = df['total_input_tokens'] * input_price
        df['output_cost'] = df['total_output_tokens'] * output_price
        df['total_cost'] = df['input_cost'] + df['output_cost']
    
    return df

# Dashboard Header
st.title("AI Thread Billing Dashboard")
st.markdown("Real-time analytics for AI thread interactions and costs")

# Initialize connections
redis_conn = get_redis_connection()
db_conn = get_db_connection()

# Sidebar for filters and controls
st.sidebar.header("Dashboard Controls")

# Auto-refresh toggle
auto_refresh = st.sidebar.checkbox("Auto-refresh (15s)", value=True)

# Add last updated time
last_updated = st.sidebar.empty()

# Use tabs for different dashboard sections
tab1, tab2, tab3 = st.tabs(["Overview", "Thread Analytics", "User Analytics"])

# Main dashboard loop
while True:
    # Update the last refresh time
    refresh_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_updated.text(f"Last updated: {refresh_time}")
    
    # Get pricing data
    pricing_df = get_token_pricing(db_conn)
    
    # OVERVIEW TAB
    with tab1:
        st.header("System Overview")
        
        # Create three columns for metrics
        col1, col2, col3 = st.columns(3)
        
        # Get overall thread and user metrics
        thread_metrics = get_thread_metrics(redis_conn, db_conn)
        user_metrics = get_user_metrics(redis_conn, db_conn)
        
        # Calculate costs
        thread_metrics = calculate_costs(thread_metrics, pricing_df)
        
        with col1:
            st.metric("Total Threads", len(thread_metrics) if not thread_metrics.empty else 0)
            st.metric("Total Users", len(user_metrics) if not user_metrics.empty else 0)
        
        with col2:
            total_messages = thread_metrics['total_messages'].sum() if not thread_metrics.empty else 0
            st.metric("Total Messages", f"{total_messages:,}")
            
            total_cost = thread_metrics['total_cost'].sum() if 'total_cost' in thread_metrics and not thread_metrics.empty else 0
            st.metric("Total Cost", f"${total_cost:.4f}")
        
        with col3:
            total_input = thread_metrics['total_input_tokens'].sum() if not thread_metrics.empty else 0
            total_output = thread_metrics['total_output_tokens'].sum() if not thread_metrics.empty else 0
            
            st.metric("Input Tokens", f"{total_input:,}")
            st.metric("Output Tokens", f"{total_output:,}")
        
        # Recent activity
        st.subheader("Recent Thread Activity")
        if not thread_metrics.empty and 'last_activity' in thread_metrics:
            # Convert to datetime
            thread_metrics['last_activity'] = pd.to_datetime(thread_metrics['last_activity'])
            
            # Sort by last activity
            recent_threads = thread_metrics.sort_values('last_activity', ascending=False).head(5)
            
            # Format for display
            if not recent_threads.empty:
                for _, thread in recent_threads.iterrows():
                    with st.expander(f"{thread['thread_title']} (ID: {thread['thread_id']})"):
                        st.write(f"User: {thread['username']}")
                        st.write(f"Messages: {thread['total_messages']}")
                        st.write(f"Last Activity: {thread['last_activity']}")
                        if 'total_cost' in thread:
                            st.write(f"Cost: ${thread['total_cost']:.4f}")
        else:
            st.info("No recent thread activity found")
    
    # THREAD ANALYTICS TAB
    with tab2:
        st.header("Thread Analytics")
        
        # Get and display thread metrics
        thread_metrics = get_thread_metrics(redis_conn, db_conn)
        thread_metrics = calculate_costs(thread_metrics, pricing_df)
        
        if not thread_metrics.empty:
            # Thread cost breakdown
            st.subheader("Thread Cost Breakdown")
            
            # Create bar chart of thread costs
            if 'total_cost' in thread_metrics:
                fig = px.bar(
                    thread_metrics.sort_values('total_cost', ascending=False).head(10),
                    x='thread_title',
                    y='total_cost',
                    title='Top 10 Threads by Cost',
                    labels={'thread_title': 'Thread', 'total_cost': 'Cost ($)'}
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Token usage by thread
            st.subheader("Token Usage by Thread")
            
            # Create grouped bar chart for token usage
            token_data = thread_metrics.sort_values('total_input_tokens', ascending=False).head(10)
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=token_data['thread_title'],
                y=token_data['total_input_tokens'],
                name='Input Tokens'
            ))
            fig.add_trace(go.Bar(
                x=token_data['thread_title'],
                y=token_data['total_output_tokens'],
                name='Output Tokens'
            ))
            fig.update_layout(
                title='Top 10 Threads by Token Usage',
                xaxis_title='Thread',
                yaxis_title='Token Count',
                barmode='group'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Detailed thread metrics table
            st.subheader("Thread Metrics Table")
            display_df = thread_metrics[['thread_id', 'thread_title', 'username', 'total_messages', 
                                        'total_input_tokens', 'total_output_tokens']]
            if 'total_cost' in thread_metrics:
                display_df['total_cost'] = thread_metrics['total_cost'].map('${:.4f}'.format)
            
            st.dataframe(display_df, use_container_width=True)
        else:
            st.info("No thread metrics available")
    
    # USER ANALYTICS TAB
    with tab3:
        st.header("User Analytics")
        
        # Get and display user metrics
        user_metrics = get_user_metrics(redis_conn, db_conn)
        
        if not user_metrics.empty:
            # User token usage
            st.subheader("Token Usage by User")
            
            token_by_user = user_metrics.groupby('username')[['total_input_tokens', 'total_output_tokens']].sum().reset_index()
            
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=token_by_user['username'],
                y=token_by_user['total_input_tokens'],
                name='Input Tokens'
            ))
            fig.add_trace(go.Bar(
                x=token_by_user['username'],
                y=token_by_user['total_output_tokens'],
                name='Output Tokens'
            ))
            fig.update_layout(
                title='Token Usage by User',
                xaxis_title='User',
                yaxis_title='Token Count',
                barmode='group'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # User activity metrics
            st.subheader("User Activity Metrics")
            
            # Group by user
            if 'thread_count' not in user_metrics:
                user_summary = user_metrics.groupby('username').agg({
                    'thread_id': 'nunique',
                    'total_messages': 'sum',
                    'total_input_tokens': 'sum',
                    'total_output_tokens': 'sum',
                    'last_activity': 'max'
                }).reset_index()
                user_summary.rename(columns={'thread_id': 'thread_count'}, inplace=True)
            else:
                user_summary = user_metrics
            
            # Display user summary
            st.dataframe(user_summary, use_container_width=True)
        else:
            st.info("No user metrics available")
    
    # Break the loop if auto-refresh is disabled
    if not auto_refresh:
        break
    
    # Sleep for the refresh interval
    time.sleep(REFRESH_INTERVAL)
    st.experimental_rerun()

# If auto-refresh is disabled, add a manual refresh button
if not auto_refresh:
    if st.button("Refresh Data"):
        st.experimental_rerun()