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
        self.client = anthropic.Client(api_key=settings.ANTHROPIC_API_KEY)
        self.default_model = "claude-3-haiku-20240307"
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
    
    def _format_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Format messages into Claude prompt format for v0.5.0"""
        prompt = ""
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "user":
                prompt += f"\n\nHuman: {content}"
            elif role == "assistant":
                prompt += f"\n\nAssistant: {content}"
            elif role == "system":
                # System messages are handled differently in Claude API
                # We'll prepend it to the first user message
                continue
        
        # Add final assistant prompt
        prompt += "\n\nAssistant:"
        return prompt
    
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
        
        # Format messages into Claude prompt format
        prompt = self._format_prompt(messages)
        
        # Count input tokens
        input_token_count = self.count_tokens(prompt)
        
        try:
            # Call Anthropic API - using the correct method for v0.5.0
            response = self.client.completions.create(
                prompt=prompt,
                model=model,
                max_tokens_to_sample=max_tokens,
                temperature=temperature,
                stop_sequences=["\n\nHuman:"]
            )
            
            # Count output tokens
            output_token_count = self.count_tokens(response.completion)
            
            # Construct result
            result = {
                "content": response.completion.strip(),
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
        
        # Format messages into Claude prompt format
        prompt = self._format_prompt(messages)
        
        # Count input tokens
        input_token_count = self.count_tokens(prompt)
        output_token_count = 0
        full_response = ""
        
        try:
            # Call Anthropic API with streaming - using the correct method for v0.5.0
            with self.client.completions.stream(
                prompt=prompt,
                model=model,
                max_tokens_to_sample=max_tokens,
                temperature=temperature,
                stop_sequences=["\n\nHuman:"]
            ) as stream:
                for completion in stream:
                    if completion.completion:
                        chunk_text = completion.completion[len(full_response):]
                        if chunk_text:
                            full_response = completion.completion
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

# Initialize a singleton instance
anthropic_service = AnthropicService()
