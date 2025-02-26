import os
import json
import time
import datetime
import asyncio
from typing import Dict, List, Optional, AsyncGenerator
import tiktoken
import anthropic
from pydantic import BaseModel
import decimal

# Custom JSON encoder to handle datetime and other non-serializable objects
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        elif isinstance(obj, decimal.Decimal):
            return float(obj)
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        else:
            return super().default(obj)

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
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.default_model = "claude-3-5-haiku-20241022"  # Update if needed
        # Initialize token counter
        self.tokenizer = tiktoken.get_encoding("cl100k_base")  # Claude uses cl100k tokenizer
    
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
        
        # Format messages for the Messages API
        formatted_messages = []
        system_message = None
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                system_message = content
            else:
                formatted_messages.append({"role": role, "content": content})
        
        # Count input tokens
        input_token_count = sum(self.count_tokens(msg["content"]) for msg in messages)
        
        try:
            # Create the request parameters
            request_params = {
                "model": model,
                "messages": formatted_messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            # Only add system parameter if we have a system message
            if system_message:
                request_params["system"] = system_message
            
            # Call Anthropic API using the Messages API
            response = await asyncio.to_thread(
                lambda: self.client.messages.create(**request_params)
            )
            
            # Count output tokens
            output_token_count = self.count_tokens(response.content[0].text)
            
            # Construct result
            result = {
                "content": response.content[0].text.strip(),
                "role": "assistant",
                "token_usage": {
                    "input_tokens": input_token_count,
                    "output_tokens": output_token_count,
                    "total_tokens": input_token_count + output_token_count
                },
                "model": model
            }
            
            return result
        
        except Exception as e:
            # Handle API errors
            error_message = f"Anthropic API Error: {str(e)}"
            print(f"Error calling Anthropic API: {str(e)}")
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

        # Format messages for the Messages API
        formatted_messages = []
        system_message = None

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                system_message = content
            else:
                formatted_messages.append({"role": role, "content": content})

        # Count input tokens
        input_token_count = sum(self.count_tokens(msg["content"]) for msg in messages)
            
        output_token_count = 0
        full_response = ""
        
        try:
            # Create request parameters
            request_params = {
                "model": model,
                "messages": formatted_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True
            }
            
            # Only add system parameter if we have a system message
            if system_message:
                request_params["system"] = system_message

            # Stream the response
            stream = await asyncio.to_thread(
                lambda: self.client.messages.create(**request_params)
            )
            
            # Process the streaming response
            async for chunk in self._process_stream(stream):
                if "content" in chunk and chunk["content"]:
                    delta = chunk["content"]
                    chunk_tokens = self.count_tokens(delta)
                    output_token_count += chunk_tokens
                    full_response += delta

                    yield {
                        "content": delta,
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
                "content": full_response.strip(),
                "role": "assistant",
                "token_usage": {
                    "input_tokens": input_token_count,
                    "output_tokens": output_token_count,
                    "total_tokens": input_token_count + output_token_count
                },
                "finish_reason": "stop",
                "model": model
            }
            
        except Exception as e:
            # Handle API errors
            error_message = f"Anthropic API Error: {str(e)}"
            print(f"Error in stream_chat_completion: {str(e)}")
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
    
    async def _process_stream(self, stream):
        """Process the Anthropic streaming response"""
        buffer = ""
        
        for chunk in stream:
            if hasattr(chunk, "type"):
                # Handle different chunk types
                if chunk.type == "content_block_delta" and hasattr(chunk, "delta"):
                    delta_text = chunk.delta.text
                    if delta_text:
                        buffer += delta_text
                        yield {"content": delta_text}
        
        # Return any remaining content
        if buffer:
            yield {"content": buffer}

# Initialize a singleton instance
anthropic_service = AnthropicService()
