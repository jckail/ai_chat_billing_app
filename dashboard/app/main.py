import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import time
import os
import redis
import json
import sqlite3
from datetime import datetime, timedelta

# Set page configuration
st.set_page_config(
    page_title="AI Thread Billing Dashboard",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# App title and description
st.title("AI Thread Billing Dashboard")
st.markdown("Real-time analytics for AI chat thread usage and costs")

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/billing.db")
REFRESH_INTERVAL = 15  # seconds

# Initialize Redis connection
@st.cache_resource
def get_redis_connection():
    try:
        return redis.from_url(REDIS_URL)
    except Exception as e:
        st.error(f"Failed to connect to Redis: {e}")
        return None

# Initialize SQLite connection
@st.cache_resource
def get_db_connection():
    try:
        # Extract path from SQLite URL
        db_path = DATABASE_URL.replace("sqlite:///", "")
        return sqlite3.connect(db_path)
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        return None

# Function to get users from database
@st.cache_data(ttl=60)  # Cache for 60 seconds
def get_users():
    conn = get_db_connection()
    if conn is None:
        return []
    
    try:
        query = "SELECT user_id, username, email FROM dim_users"
        df = pd.read_sql_query(query, conn)
        return df.to_dict('records')
    except Exception as e:
        st.error(f"Failed to fetch users: {e}")
        return []
    finally:
        conn.close()

# Function to get thread metrics
@st.cache_data(ttl=REFRESH_INTERVAL)  # Cache for the refresh interval
def get_thread_metrics(user_id=None):
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    
    try:
        # Base query
        query = """
        SELECT 
            ut.thread_id,
            ut.title,
            ut.created_at,
            ut.updated_at,
            COUNT(utm.message_id) AS message_count,
            dm.model_name,
            SUM(CASE WHEN mt.token_type = 'input' THEN mt.token_count ELSE 0 END) AS input_tokens,
            SUM(CASE WHEN mt.token_type = 'output' THEN mt.token_count ELSE 0 END) AS output_tokens
        FROM 
            user_threads ut
        LEFT JOIN 
            user_thread_messages utm ON ut.thread_id = utm.thread_id
        LEFT JOIN 
            message_tokens mt ON utm.message_id = mt.message_id
        LEFT JOIN
            dim_models dm ON ut.model_id = dm.model_id
        """
        
        # Add user filter if provided
        if user_id:
            query += f" WHERE ut.user_id = {user_id}"
        
        # Group and order
        query += """
        GROUP BY 
            ut.thread_id
        ORDER BY 
            ut.updated_at DESC
        """
        
        df = pd.read_sql_query(query, conn)
        
        # Calculate costs (using default pricing for simplicity)
        input_price = 0.00000025  # $0.25 per million tokens
        output_price = 0.00000075  # $0.75 per million tokens
        
        df['input_cost'] = df['input_tokens'] * input_price
        df['output_cost'] = df['output_tokens'] * output_price
        df['total_cost'] = df['input_cost'] + df['output_cost']
        
        # Format dates
        df['created_at'] = pd.to_datetime(df['created_at'])
        df['updated_at'] = pd.to_datetime(df['updated_at'])
        
        return df
    
    except Exception as e:
        st.error(f"Failed to fetch thread metrics: {e}")
        return pd.DataFrame()
    
    finally:
        conn.close()

# Function to get message details for a thread
@st.cache_data(ttl=REFRESH_INTERVAL)
def get_thread_messages(thread_id):
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    
    try:
        query = """
        SELECT 
            utm.message_id,
            utm.content,
            utm.role,
            utm.created_at,
            SUM(CASE WHEN mt.token_type = 'input' THEN mt.token_count ELSE 0 END) AS input_tokens,
            SUM(CASE WHEN mt.token_type = 'output' THEN mt.token_count ELSE 0 END) AS output_tokens
        FROM 
            user_thread_messages utm
        LEFT JOIN 
            message_tokens mt ON utm.message_id = mt.message_id
        WHERE 
            utm.thread_id = ?
        GROUP BY 
            utm.message_id
        ORDER BY 
            utm.created_at
        """
        
        df = pd.read_sql_query(query, conn, params=(thread_id,))
        
        # Calculate costs
        input_price = 0.00000025  # $0.25 per million tokens
        output_price = 0.00000075  # $0.75 per million tokens
        
        df['input_cost'] = df['input_tokens'] * input_price
        df['output_cost'] = df['output_tokens'] * output_price
        df['total_cost'] = df['input_cost'] + df['output_cost']
        
        # Format dates
        df['created_at'] = pd.to_datetime(df['created_at'])
        
        return df
    
    except Exception as e:
        st.error(f"Failed to fetch thread messages: {e}")
        return pd.DataFrame()
    
    finally:
        conn.close()

# Sidebar - User Selection
st.sidebar.header("Filters")

users = get_users()
user_options = [{"user_id": None, "username": "All Users"}] + users
selected_user = st.sidebar.selectbox(
    "Select User",
    options=user_options,
    format_func=lambda x: x["username"],
    index=0
)

user_id_filter = selected_user["user_id"] if selected_user else None

# Auto-refresh control
auto_refresh = st.sidebar.checkbox("Auto-refresh (15s)", value=True)
if auto_refresh:
    st.sidebar.write(f"Dashboard will refresh every {REFRESH_INTERVAL} seconds")

refresh_button = st.sidebar.button("Refresh Now")

# Main dashboard area
col1, col2 = st.columns(2)

with col1:
    st.subheader("Thread Activity")
    
    # Get thread metrics
    thread_metrics = get_thread_metrics(user_id_filter)
    
    if not thread_metrics.empty:
        # Calculate total stats
        total_threads = len(thread_metrics)
        total_messages = thread_metrics['message_count'].sum()
        total_cost = thread_metrics['total_cost'].sum()
        
        # Display metrics
        metric_col1, metric_col2, metric_col3 = st.columns(3)
        metric_col1.metric("Total Threads", total_threads)
        metric_col2.metric("Total Messages", int(total_messages))
        metric_col3.metric("Total Cost", f"${total_cost:.4f}")
        
        # Thread activity chart
        thread_activity = thread_metrics.copy()
        thread_activity['date'] = thread_activity['updated_at'].dt.date
        activity_by_date = thread_activity.groupby('date').size().reset_index(name='count')
        activity_by_date['date'] = pd.to_datetime(activity_by_date['date'])
        
        fig = px.bar(
            activity_by_date,
            x='date',
            y='count',
            title="Thread Activity by Date",
            labels={'count': 'Thread Updates', 'date': 'Date'}
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No thread data available")

with col2:
    st.subheader("Cost Distribution")
    
    if not thread_metrics.empty:
        # Cost distribution by thread
        fig = px.pie(
            thread_metrics,
            values='total_cost',
            names='title',
            title="Cost Distribution by Thread",
            hole=0.4
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Token usage by thread
        token_usage = thread_metrics[['title', 'input_tokens', 'output_tokens']].copy()
        token_usage = token_usage.melt(
            id_vars=['title'],
            value_vars=['input_tokens', 'output_tokens'],
            var_name='Token Type',
            value_name='Count'
        )
        
        fig = px.bar(
            token_usage,
            x='title',
            y='Count',
            color='Token Type',
            title="Token Usage by Thread",
            barmode='group'
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No cost data available")

# Thread details
st.subheader("Thread Details")

if not thread_metrics.empty:
    # Format the dataframe for display
    display_threads = thread_metrics[['thread_id', 'title', 'model_name', 'message_count', 'input_tokens', 'output_tokens', 'total_cost', 'updated_at']].copy()
    display_threads['total_cost'] = display_threads['total_cost'].apply(lambda x: f"${x:.6f}")
    display_threads['updated_at'] = display_threads['updated_at'].dt.strftime('%Y-%m-%d %H:%M:%S')
    display_threads = display_threads.rename(columns={
        'thread_id': 'ID',
        'title': 'Title',
        'model_name': 'Model',
        'message_count': 'Messages',
        'input_tokens': 'Input Tokens',
        'output_tokens': 'Output Tokens',
        'total_cost': 'Cost',
        'updated_at': 'Last Activity'
    })
    
    st.dataframe(display_threads, use_container_width=True)
    
    # Thread selection for detailed view
    selected_thread_id = st.selectbox(
        "Select Thread for Detailed View",
        options=thread_metrics['thread_id'].tolist(),
        format_func=lambda x: f"Thread {x}: {thread_metrics[thread_metrics['thread_id'] == x]['title'].iloc[0]}"
    )
    
    if selected_thread_id:
        st.subheader(f"Messages for Thread: {thread_metrics[thread_metrics['thread_id'] == selected_thread_id]['title'].iloc[0]}")
        
        messages = get_thread_messages(selected_thread_id)
        
        if not messages.empty:
            # Message cost chart
            fig = px.line(
                messages,
                x='created_at',
                y='total_cost',
                title="Message Cost Over Time",
                labels={'total_cost': 'Cost ($)', 'created_at': 'Time'}
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Message details
            for idx, row in messages.iterrows():
                with st.expander(f"{row['role'].title()}: {row['created_at'].strftime('%Y-%m-%d %H:%M:%S')} - Cost: ${row['total_cost']:.6f}"):
                    st.write(row['content'])
                    st.caption(f"Input Tokens: {row['input_tokens']}, Output Tokens: {row['output_tokens']}")
        else:
            st.info("No messages found for this thread")
else:
    st.info("No threads available")

# Auto-refresh logic
if auto_refresh:
    time.sleep(1)  # Small delay to allow UI to render
    st.empty()  # This is needed for the rerun to work properly
    time.sleep(REFRESH_INTERVAL - 1)  # Subtract the 1 second delay from above
    st.experimental_rerun()

if refresh_button:
    st.experimental_rerun()

# Footer
st.markdown("---")
st.caption("AI Thread Billing Dashboard - Refreshes every 15 seconds")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")