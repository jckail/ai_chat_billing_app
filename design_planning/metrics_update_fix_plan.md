# AI Thread Billing Metrics Update Fix Plan

## Problem Statement

As observed in the attached screenshot, the chat application is not properly updating token usage and cost metrics when messages are sent and received. Despite there being 16 messages in the thread, the metrics display shows:

- Input Tokens: 0
- Output Tokens: 0
- Total Cost: $0.000000

This indicates a failure in either the token tracking, storage, or display components of the system.

## Code Analysis Findings

After reviewing the source code, I've identified several issues that could be causing the metrics to not update properly:

### 1. Token Tracking Issues

- **Dual Token Storage Approach**: The system uses two parallel approaches to track tokens:
  - Primary: The `MessageToken` table (dedicated token records)
  - Fallback: The `UserThreadMessage.token_count` field (simplified tracking)

- **Inconsistent Data**: In `billing.py` (lines 136-154), there's a fallback mechanism that checks `UserThreadMessage.token_count` if no records are found in the `MessageToken` table, but it appears neither source is being populated consistently.

- **Message Type Mismatch**: Token types (input/output) should align with message roles (user/assistant), but there might be inconsistencies.

### 2. Message Processing Flow Issues

- In `message_processor.py`, the `handle_token_metrics` function (line 66) is responsible for storing token counts when processing Kafka events.

- Token records should be created in lines 112-166, but these operations may be failing or not being triggered.

- Cache invalidation occurs in lines 173-175, but this might not be working as expected.

### 3. Metric Calculation Issues

- The backend's `billing.py` endpoint attempts to calculate metrics from both token sources but may receive empty values.

- When recalculating metrics in `message_processor.py:update_thread_metrics_cache` (line 188), the function correctly tries both sources, but neither may contain valid data.

### 4. Frontend Timing Issues

- The frontend attempts to refresh metrics after sending/receiving messages using `setTimeout` with delays (3-5 seconds in App.js lines 149 and 288).

- These delays might not be sufficient for the backend to process tokens, especially if Kafka processing is backed up.

## Implementation Plan

### 1. Backend Fixes

#### 1.1 Fix Token Counting in Anthropic Service

First, let's ensure token counts are being properly tracked in `anthropic_service.py`:

```python
# Add consistent token counting in the service
async def send_message(content, thread_id, model_id):
    # ... existing code ...
    
    # Count tokens in the input (user message)
    input_tokens = count_tokens(content)
    
    # Store input token count with the user message
    user_message = UserThreadMessage(
        thread_id=thread_id,
        user_id=user_id,
        content=content,
        role="user",
        model_id=model_id,
        token_count=input_tokens  # Explicitly set token count
    )
    
    # ... call API and process response ...
    
    # Count tokens in the output (assistant response)
    output_tokens = response.usage.output_tokens
    
    # Store output token count with assistant message
    assistant_message = UserThreadMessage(
        thread_id=thread_id,
        user_id=user_id,
        content=response_content,
        role="assistant",
        model_id=model_id,
        token_count=output_tokens  # Explicitly set token count
    )
    
    # Ensure token records exist in MessageToken table
    input_token_record = MessageToken(
        message_id=user_message.message_id,
        token_type="input",
        token_count=input_tokens
    )
    
    output_token_record = MessageToken(
        message_id=assistant_message.message_id,
        token_type="output",
        token_count=output_tokens
    )
    
    db.add_all([input_token_record, output_token_record])
    db.commit()
    
    # Publish token metrics to Kafka for further processing
    await kafka_service.publish_message("token_metrics", {
        "message_id": assistant_message.message_id,
        "model_id": model_id,
        "token_usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }
    })
```

#### 1.2 Improve Message Processor Logic

Next, let's fix the `handle_token_metrics` function in `message_processor.py`:

```python
async def handle_token_metrics(data: Dict[str, Any], db: Optional[Session] = None):
    """Process token metrics from the Kafka topic"""
    logger.info(f"[BILLING] Processing token metrics for message {data.get('message_id')}")
    
    if db is None:
        db = SessionLocal()
        close_db = True
    else:
        close_db = False
    
    try:
        message_id = data.get('message_id')
        model_id = data.get('model_id')
        token_usage = data.get('token_usage', {"input_tokens": 0, "output_tokens": 0})
        
        if not message_id or not model_id:
            logger.error("[BILLING] Missing required data in token metrics")
            return
        
        # Get the message to check thread_id and user_id
        message = db.query(UserThreadMessage).filter(
            UserThreadMessage.message_id == message_id
        ).first()
        
        if not message:
            logger.error(f"[BILLING] Message not found: {message_id}")
            return
            
        # Update the message's token_count field directly
        if message.role == 'user':
            input_tokens = token_usage.get('input_tokens', 0)
            message.token_count = input_tokens
        else:
            output_tokens = token_usage.get('output_tokens', 0)
            message.token_count = output_tokens
        
        # Get current token pricing
        pricing = db.query(DimTokenPricing).filter(
            DimTokenPricing.model_id == model_id,
            DimTokenPricing.is_current == True
        ).first()
        
        if not pricing:
            logger.warning(f"[BILLING] No pricing found for model {model_id}, using defaults")
            input_price = settings.DEFAULT_INPUT_TOKEN_PRICE
            output_price = settings.DEFAULT_OUTPUT_TOKEN_PRICE
        else:
            input_price = pricing.input_token_price
            output_price = settings.DEFAULT_OUTPUT_TOKEN_PRICE
        
        # Process token records
        input_tokens = token_usage.get('input_tokens', 0)
        output_tokens = token_usage.get('output_tokens', 0)

        logger.info(f"[BILLING] Token usage for message {message_id}: Input={input_tokens}, Output={output_tokens}")
        
        # Always create or update token records, don't check for existing
        if input_tokens > 0:
            # Delete any existing input token records for this message
            db.query(MessageToken).filter(
                MessageToken.message_id == message_id,
                MessageToken.token_type == "input"
            ).delete()
            
            # Create new token record
            token_record = MessageToken(
                message_id=message_id,
                token_type="input",
                token_count=input_tokens
            )
            db.add(token_record)
            db.flush()
            
            # Create invoice line item
            if pricing:
                line_item = UserInvoiceLineItem(
                    message_id=message_id,
                    token_id=token_record.token_id,
                    pricing_id=pricing.pricing_id,
                    amount=input_tokens * input_price
                )
                db.add(line_item)
        
        if output_tokens > 0:
            # Delete any existing output token records for this message
            db.query(MessageToken).filter(
                MessageToken.message_id == message_id,
                MessageToken.token_type == "output"
            ).delete()
            
            # Create new token record
            token_record = MessageToken(
                message_id=message_id,
                token_type="output",
                token_count=output_tokens
            )
            db.add(token_record)
            db.flush()
            
            # Create invoice line item
            if pricing:
                line_item = UserInvoiceLineItem(
                    message_id=message_id,
                    token_id=token_record.token_id,
                    pricing_id=pricing.pricing_id,
                    amount=output_tokens * output_price
                )
                db.add(line_item)
        
        # Commit changes
        db.commit()
        logger.info(f"[BILLING] Successfully committed token records and invoice items")

        # Completely clear the cache for metrics
        logger.info(f"[BILLING] Invalidating cached metrics for thread {message.thread_id}")
        await redis_service.delete_value('thread_metrics', message.thread_id)
        await redis_service.delete_value('user_metrics', message.user_id)
        
        # Recalculate and cache new metrics after a short delay to ensure DB consistency
        await asyncio.sleep(1)
        logger.info(f"[BILLING] Recalculating metrics for thread {message.thread_id}")
        await update_thread_metrics_cache(message.thread_id, db)
        
    except Exception as e:
        logger.error(f"[BILLING] Error processing token metrics: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        db.rollback()
    finally:
        if close_db:
            db.close()
```

#### 1.3 Enhance Billing API Endpoint

Let's improve the thread metrics endpoint in `billing.py`:

```python
@router.get("/metrics/thread/{thread_id}", response_model=BillingMetrics)
async def get_thread_billing_metrics(
    thread_id: int, 
    refresh: bool = False,
    db: Session = Depends(get_db)
):
    """Get billing metrics for a specific thread"""
    logger.info(f"[BILLING] Metrics requested for thread {thread_id}" + 
                f"{' (forced refresh)' if refresh else ''}")
    
    # Check if thread exists
    thread = db.query(UserThread).filter(UserThread.thread_id == thread_id).first()
    if not thread:
        logger.error(f"Thread {thread_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )
    
    # Try to get metrics from cache unless refresh is requested
    cached_metrics = None
    if refresh:
        # Force clear the cache for this thread
        logger.info(f"[BILLING] Forcing cache refresh for thread {thread_id}")
        await redis_service.force_refresh_thread_metrics(thread_id)
    else:
        cached_metrics = await redis_service.get_thread_metrics(thread_id)
        if cached_metrics:
            logger.info(f"[BILLING] Using cached metrics for thread {thread_id}: {cached_metrics}")
            return cached_metrics
    
    # Get message count
    message_count = db.query(func.count(UserThreadMessage.message_id)) \
        .filter(UserThreadMessage.thread_id == thread_id) \
        .scalar() or 0
    
    # First try to get token counts from UserThreadMessage table (more reliable)
    user_input_tokens = db.query(func.sum(UserThreadMessage.token_count)) \
        .filter(UserThreadMessage.thread_id == thread_id, 
                UserThreadMessage.role == 'user',
                UserThreadMessage.token_count != None) \
        .scalar() or 0
    
    assistant_output_tokens = db.query(func.sum(UserThreadMessage.token_count)) \
        .filter(UserThreadMessage.thread_id == thread_id, 
                UserThreadMessage.role == 'assistant',
                UserThreadMessage.token_count != None) \
        .scalar() or 0
    
    # Initialize token counts
    input_tokens = user_input_tokens
    output_tokens = assistant_output_tokens
    
    # If we didn't get tokens from the messages table, try the token table
    if input_tokens == 0 and output_tokens == 0:
        logger.warning(f"[BILLING] No tokens found in UserThreadMessage, checking MessageToken table")
        
        # Get token counts from MessageToken table
        token_metrics = db.query(
                MessageToken.token_type,
                func.sum(MessageToken.token_count).label('token_count')
            ) \
            .join(UserThreadMessage, UserThreadMessage.message_id == MessageToken.message_id) \
            .filter(UserThreadMessage.thread_id == thread_id) \
            .group_by(MessageToken.token_type) \
            .all()
        
        # Process token metrics
        for token_type, count in token_metrics:
            if token_type == "input":
                input_tokens = count
            elif token_type == "output":
                output_tokens = count
    
    logger.info(f"[BILLING] Found tokens: input={input_tokens}, output={output_tokens}")
    
    # Get the latest pricing
    pricing = db.query(DimTokenPricing) \
        .filter(DimTokenPricing.is_current == True) \
        .order_by(desc(DimTokenPricing.effective_from)) \
        .first()
    
    # Use default pricing if not found
    input_price = settings.DEFAULT_INPUT_TOKEN_PRICE
    output_price = settings.DEFAULT_OUTPUT_TOKEN_PRICE
    
    if pricing:
        input_price = pricing.input_token_price
        output_price = pricing.output_token_price
    
    # Calculate cost
    total_cost = round((input_tokens * input_price) + (output_tokens * output_price), 6)
    logger.info(f"[BILLING] Calculated total cost for thread {thread_id}: {total_cost}")
    
    # Get last activity time
    last_activity = db.query(func.max(UserThreadMessage.created_at)) \
        .filter(UserThreadMessage.thread_id == thread_id) \
        .scalar()
    
    metrics = {
        "thread_id": thread_id,
        "total_messages": message_count,
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "total_cost": total_cost,
        "last_activity": last_activity or thread.created_at
    }
    
    # Cache the metrics
    logger.info(f"[BILLING] Caching new metrics for thread {thread_id}: {metrics}")
    asyncio.create_task(redis_service.cache_thread_metrics(thread_id, metrics))
    
    return metrics
```

### 2. Frontend Improvements

Let's make the following adjustments to `App.js`:

1. **Increase the delay time for metric refreshes**:

```javascript
// Adjust line 149 in App.js - when a message completes
setTimeout(() => {
  // Use refresh=true to force a fresh calculation
  setRefreshingMetrics(true);
  fetchThreadMetrics(currentThread.thread_id, true)
    .then(() => setRefreshingMetrics(false));
  console.log("[BILLING] Fetching updated thread metrics after message completion (with refresh)");
}, 5000); // Increased from 3 to 5 seconds

// Adjust line 288 in App.js - after message send
setTimeout(() => {
  console.log("[BILLING] Fetching metrics after WebSocket message send");
  setRefreshingMetrics(true);
  fetchThreadMetrics(currentThread.thread_id, true)
    .then(() => setRefreshingMetrics(false));
}, 8000); // Increased from 5 to 8 seconds
```

2. **Add retry logic for metrics**:

```javascript
// Modify the fetchThreadMetrics function around line 317
const fetchThreadMetrics = async (threadId, refresh = false, retryCount = 0) => {
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
      // Wait a bit longer and retry
      await new Promise(resolve => setTimeout(resolve, 3000));
      return fetchThreadMetrics(threadId, true, retryCount + 1);
    }
    
    setThreadMetrics(response.data);
    return response.data;
  } catch (error) {
    console.error('[BILLING] Error fetching thread metrics:', error);
    
    // On error, retry if we haven't tried too many times
    if (retryCount < 3) {
      console.log(`[BILLING] Retrying metrics fetch (attempt ${retryCount + 1}/3)`);
      await new Promise(resolve => setTimeout(resolve, 2000));
      return fetchThreadMetrics(threadId, refresh, retryCount + 1);
    }
    
    return null;
  }
};
```

3. **Add a debug message display in the UI**:

```jsx
// Add this inside the billing tab (around line 650)
{threadMetrics && (
  <Box sx={{ mt: 2, p: 2, bgcolor: '#f5f5f5', borderRadius: 1 }}>
    <Typography variant="subtitle2" gutterBottom>Debug Information:</Typography>
    <Typography variant="caption" component="div">
      Last metrics update: {new Date().toLocaleTimeString()}
    </Typography>
    <Typography variant="caption" component="div">
      Messages: {threadMetrics.total_messages}
    </Typography>
    <Typography variant="caption" component="div">
      Raw cost calculation: ({threadMetrics.total_input_tokens} × ${TOKEN_PRICING.INPUT_PRICE}) + 
      ({threadMetrics.total_output_tokens} × ${TOKEN_PRICING.OUTPUT_PRICE}) = 
      ${formatCurrency(threadMetrics.total_cost)}
    </Typography>
  </Box>
)}
```

## Testing Plan

1. **Backend Testing**:
   - Add direct logging to the console when token counts are stored
   - Run queries to verify token counts are being saved correctly
   - Monitor Redis cache updates

2. **Frontend Testing**:
   - Watch the network requests to see if metrics are being fetched
   - Check browser console for any errors
   - Monitor the debug information to see what values are being returned

## Rollout Strategy

1. Implement the backend changes first
2. Test with the existing frontend
3. If metrics still don't update correctly, implement the frontend changes
4. Monitor the system to ensure metrics display properly

By focusing on these specific fixes, we should be able to get the metrics updating properly for each message in the chat thread.