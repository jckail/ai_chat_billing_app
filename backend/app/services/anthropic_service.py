import os
import json
import time
import asyncio
from typing import Dict, List, Optional, AsyncGenerator
import tiktoken
import anthropic
from anthropic import Anthropic
from pydantic import BaseModel

from app.core.config import settings

class Message(BaseModel):
    role: str
    content: str

class TokenCount(BaseModel):
    input_tokens: int
    output_tokens: int

class AnthropicService:
    """Service for interacting with the Anthropic API"""
    
    def __init__(self):
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.default_model = "claude-3-5-haiku"
        # Initialize token counter
        self.tokenizer = tiktoken.encoding_for_model("cl100k_base")  # Claude uses cl100k tokenizer
    
    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in a text string"""
        if not text:
            return 0
        return len(self.tokenizer.encode(text))
    
    def count_message_tokens(self, messages: List[Message]) -> TokenCount:
        """Count tokens in a list of messages"""
        input_tokens = 0
        
        for message in messages:
            input_tokens += self.count_tokens(message.content)
            # Add a small constant for message role and formatting
            input_tokens += 4  # Approximate overhead per message
        
        # System message and additional format tokens
        input_tokens += 20
        
        return TokenCount(input_tokens=input_tokens, output_tokens=0)
    
    async def create_chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        model: str = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> Dict:
        """
        Create a chat completion with the Anthropic API
        
        Args:
            messages: List of message objects with role and content
            model: Model to use (defaults to claude-3-5-haiku)
            max_tokens: Maximum tokens in the response
            temperature: Sampling temperature
            
        Returns:
            Dict with response and token usage
        """
        model = model or self.default_model
        
        # Format messages for Anthropic
        anthropic_messages = []
        for msg in messages:
            anthropic_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        # Count input tokens
        input_token_count = self.count_tokens(json.dumps(anthropic_messages))
        
        try:
            # Call Anthropic API
            response = await asyncio.to_thread(
                self.client.messages.create,
                model=model,
                messages=anthropic_messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            # Count output tokens
            output_token_count = self.count_tokens(response.content[0].text)
            
            # Construct result
            result = {
                "content": response.content[0].text,
                "role": "assistant",
                "token_usage": {
                    "input_tokens": input_token_count,
                    "output_tokens": output_token_count,
                    "total_tokens": input_token_count + output_token_count
                },
                "model": model
            }
            
            return result
        
        except anthropic.APIError as e:
            # Handle API errors
            error_message = f"Anthropic API Error: {str(e)}"
            return {
                "content": error_message,
                "role": "assistant",
                "token_usage": {
                    "input_tokens": input_token_count,
                    "output_tokens": 0,
                    "total_tokens": input_token_count
                },
                "error": str(e),
                "model": model
            }
    
    async def stream_chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        model: str = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncGenerator[Dict, None]:
        """
        Stream a chat completion with the Anthropic API
        
        Args:
            messages: List of message objects with role and content
            model: Model to use (defaults to claude-3-5-haiku)
            max_tokens: Maximum tokens in the response
            temperature: Sampling temperature
            
        Yields:
            Dictionary with response content chunks and token counts
        """
        model = model or self.default_model
        
        # Format messages for Anthropic
        anthropic_messages = []
        for msg in messages:
            anthropic_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        # Count input tokens
        input_token_count = self.count_tokens(json.dumps(anthropic_messages))
        output_token_count = 0
        full_response = ""
        
        try:
            # Call Anthropic API with streaming
            stream = await asyncio.to_thread(
                self.client.messages.create,
                model=model,
                messages=anthropic_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True
            )
            
            # Stream the response
            async for chunk in stream:
                if chunk.type == "content_block_delta" and chunk.delta.text:
                    chunk_text = chunk.delta.text
                    full_response += chunk_text
                    chunk_tokens = self.count_tokens(chunk_text)
                    output_token_count += chunk_tokens
                    
                    yield {
                        "content": chunk_text,
                        "role": "assistant",
                        "token_usage": {
                            "input_tokens": input_token_count,
                            "output_tokens": output_token_count,
                            "total_tokens": input_token_count + output_token_count
                        },
                        "finish_reason": None,
                        "model": model
                    }
            
            # Final yield with complete information
            yield {
                "content": full_response,
                "role": "assistant",
                "token_usage": {
                    "input_tokens": input_token_count,
                    "output_tokens": output_token_count,
                    "total_tokens": input_token_count + output_token_count
                },
                "finish_reason": "stop",
                "model": model
            }
            
        except anthropic.APIError as e:
            # Handle API errors
            error_message = f"Anthropic API Error: {str(e)}"
            yield {
                "content": error_message,
                "role": "assistant",
                "token_usage": {
                    "input_tokens": input_token_count,
                    "output_tokens": 0,
                    "total_tokens": input_token_count
                },
                "error": str(e),
                "finish_reason": "error",
                "model": model
            }

# Initialize a singleton instance
anthropic_service = AnthropicService()