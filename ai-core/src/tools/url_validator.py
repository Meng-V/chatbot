"""URL Validator - Verifies ALL URLs before they are provided to users.

This module prevents the bot from providing fake or dead URLs by:
1. Checking if URLs return 4xx or 5xx errors
2. Validating ALL URLs regardless of domain
3. Extracting and validating all URLs from agent responses

NO WHITELIST - All URLs must be verified before being shown to users.
"""

import re
import httpx
from typing import List, Dict, Tuple
from urllib.parse import urlparse
import asyncio


# URL pattern (basic)
URL_PATTERN = r'https?://[^\s<>"{}|\\^`\[\]]+'


async def check_url_exists(url: str, timeout: float = 5.0) -> Tuple[bool, int, str]:
    """Check if a URL exists and is accessible (not 404).
    
    Args:
        url: URL to check
        timeout: Request timeout in seconds
        
    Returns:
        Tuple of (exists: bool, status_code: int, error_message: str)
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.head(url)
            
            # Consider 2xx and 3xx as valid
            if 200 <= response.status_code < 400:
                return True, response.status_code, ""
            
            # Reject all 4xx (client errors) and 5xx (server errors)
            if 400 <= response.status_code < 500:
                return False, response.status_code, f"Client error ({response.status_code})"
            
            if response.status_code >= 500:
                return False, response.status_code, f"Server error ({response.status_code})"
            
            return False, response.status_code, f"URL returned status {response.status_code}"
            
    except httpx.TimeoutException:
        return False, 0, "URL request timed out"
    except httpx.ConnectError:
        return False, 0, "Could not connect to URL"
    except Exception as e:
        return False, 0, f"Error checking URL: {str(e)}"


def extract_urls_from_text(text: str) -> List[str]:
    """Extract all URLs from text.
    
    Args:
        text: Text to extract URLs from
        
    Returns:
        List of URLs found in text
    """
    # Find all URLs
    urls = re.findall(URL_PATTERN, text)
    
    # Clean up URLs (remove trailing punctuation)
    cleaned_urls = []
    for url in urls:
        # Remove trailing punctuation that's not part of URL
        url = re.sub(r'[.,;:!?)]+$', '', url)
        cleaned_urls.append(url)
    
    return list(set(cleaned_urls))  # Remove duplicates


async def validate_urls_in_text(text: str, log_callback=None) -> Dict[str, any]:
    """Validate ALL URLs in text and return results.
    
    NO WHITELIST - All URLs are validated regardless of domain.
    
    Args:
        text: Text containing URLs to validate
        log_callback: Optional logging function
        
    Returns:
        Dictionary with validation results:
        {
            "valid_urls": List of valid URLs,
            "invalid_urls": List of invalid URLs with reasons,
            "all_urls_valid": Boolean indicating if all URLs are valid
        }
    """
    if log_callback:
        log_callback("🔍 [URL Validator] Extracting URLs from response")
    
    # Extract all URLs from text
    urls = extract_urls_from_text(text)
    
    if not urls:
        if log_callback:
            log_callback("✅ [URL Validator] No URLs found in response")
        return {
            "valid_urls": [],
            "invalid_urls": [],
            "all_urls_valid": True
        }
    
    if log_callback:
        log_callback(f"🔍 [URL Validator] Found {len(urls)} URL(s) - validating ALL")
    
    valid_urls = []
    invalid_urls = []
    
    # Validate ALL URLs in parallel
    tasks = [check_url_exists(url) for url in urls]
    results = await asyncio.gather(*tasks)
    
    for url, (exists, status_code, error_msg) in zip(urls, results):
        if exists:
            valid_urls.append(url)
            if log_callback:
                log_callback(f"✅ [URL Validator] Valid ({status_code}): {url}")
        else:
            invalid_urls.append({
                "url": url,
                "status_code": status_code,
                "error": error_msg
            })
            if log_callback:
                log_callback(f"❌ [URL Validator] Invalid: {url} - {error_msg}")
    
    all_valid = len(invalid_urls) == 0
    
    if log_callback:
        log_callback(f"📊 [URL Validator] Results: {len(valid_urls)} valid, {len(invalid_urls)} invalid")
    
    return {
        "valid_urls": valid_urls,
        "invalid_urls": invalid_urls,
        "all_urls_valid": all_valid
    }


def remove_invalid_urls_from_text(text: str, invalid_urls: List[Dict]) -> str:
    """Remove invalid URLs from text and add disclaimers.
    
    Args:
        text: Original text with URLs
        invalid_urls: List of invalid URL dictionaries
        
    Returns:
        Text with invalid URLs removed and disclaimers added
    """
    if not invalid_urls:
        return text
    
    modified_text = text
    
    # Remove each invalid URL and add a disclaimer
    for invalid in invalid_urls:
        url = invalid["url"]
        error = invalid["error"]
        
        # Remove the URL from text
        # Try to remove the whole sentence/line if it's primarily about the URL
        modified_text = modified_text.replace(url, "[URL removed - not accessible]")
    
    # Add disclaimer at the end if any URLs were removed
    if len(invalid_urls) > 0:
        disclaimer = "\n\n⚠️ Note: Some URLs were removed because they are not currently accessible. "
        disclaimer += "I apologize for any inconvenience. Please contact a librarian for the most up-to-date information."
        modified_text += disclaimer
    
    return modified_text


async def validate_and_clean_response(response_text: str, log_callback=None) -> Tuple[str, bool]:
    """Validate URLs in response and remove invalid ones.
    
    This is the main function to call before returning a response to the user.
    
    Args:
        response_text: The response text to validate
        log_callback: Optional logging function
        
    Returns:
        Tuple of (cleaned_text: str, had_invalid_urls: bool)
    """
    # Validate all URLs
    validation_results = await validate_urls_in_text(response_text, log_callback)
    
    # If all URLs are valid, return original text
    if validation_results["all_urls_valid"]:
        return response_text, False
    
    # Remove invalid URLs and add disclaimers
    cleaned_text = remove_invalid_urls_from_text(
        response_text, 
        validation_results["invalid_urls"]
    )
    
    if log_callback:
        log_callback(f"🔧 [URL Validator] Cleaned response - removed {len(validation_results['invalid_urls'])} invalid URL(s)")
    
    return cleaned_text, True
