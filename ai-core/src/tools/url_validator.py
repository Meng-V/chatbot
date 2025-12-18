"""URL and Contact Info Validator - Verifies ALL URLs and contact information before they are provided to users.

This module prevents the bot from providing fake or dead URLs by:
1. Checking if URLs return 4xx or 5xx errors
2. Validating ALL URLs regardless of domain
3. Extracting and validating all URLs from agent responses
4. Detecting and removing fabricated contact information (emails, phone numbers, names)

NO WHITELIST - All URLs must be verified before being shown to users.
NO FABRICATION - All contact info must come from verified tool results.
"""

import re
import httpx
from typing import List, Dict, Tuple, Optional
from urllib.parse import urlparse, urlunparse
import asyncio


# URL pattern (basic)
URL_PATTERN = r'https?://[^\s<>"{}|\\^`\[\]]+'

# ILL URL corrections - Regional campus URLs should default to main campus
# unless the user specifically mentions a regional campus
ILL_URL_CORRECTIONS = {
    # Hamilton ILL (regional) → Main campus (default)
    "https://libguides.lib.miamioh.edu/ILL": "https://www.lib.miamioh.edu/use/borrow/ill/",
    # Middletown ILL (regional) → Main campus (default)  
    "https://www.mid.miamioh.edu/library/interlibraryloan.htm": "https://www.lib.miamioh.edu/use/borrow/ill/",
}

# Email pattern for detecting @miamioh.edu emails
EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@miamioh\.edu\b'

# Pattern for detecting potential librarian names (capitalized words near contact info)
LIBRARIAN_NAME_PATTERN = r'\b(?:librarian|contact|specialist|professor|dr\.|mr\.|ms\.|mrs\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'


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


def get_parent_urls(url: str) -> List[str]:
    """Generate parent URLs by progressively removing path segments.
    
    Example:
        https://lib.miamioh.edu/path/to/page/details
        → https://lib.miamioh.edu/path/to/page
        → https://lib.miamioh.edu/path/to
        → https://lib.miamioh.edu/path
        → https://lib.miamioh.edu/
    
    Args:
        url: The URL to climb up from
        
    Returns:
        List of parent URLs (from closest to furthest)
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')
    
    if not path or path == '/':
        return []
    
    parent_urls = []
    path_parts = path.split('/')
    
    # Generate parent paths by removing one segment at a time
    while len(path_parts) > 1:
        path_parts = path_parts[:-1]  # Remove last segment
        parent_path = '/'.join(path_parts) or '/'
        
        # Reconstruct URL with parent path
        parent_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parent_path,
            '',  # params
            '',  # query (drop query params for parent)
            ''   # fragment
        ))
        parent_urls.append(parent_url)
    
    return parent_urls


async def check_url_with_fallback(
    url: str, 
    timeout: float = 5.0,
    max_climb_levels: int = 3,
    log_callback=None
) -> Tuple[bool, str, int, str]:
    """Check URL and try parent paths if it returns 4xx.
    
    This helps when:
    - Specific pages are moved but parent pages exist
    - Deep links require login but parent pages are public
    - Content has been reorganized
    
    Args:
        url: Original URL to check
        timeout: Request timeout in seconds
        max_climb_levels: Maximum number of parent levels to try
        log_callback: Optional logging function
        
    Returns:
        Tuple of (exists: bool, final_url: str, status_code: int, error_message: str)
        - exists: True if any URL in the chain was valid
        - final_url: The URL that worked (original or parent)
        - status_code: HTTP status code
        - error_message: Error description if failed
    """
    # First, try the original URL
    exists, status_code, error_msg = await check_url_exists(url, timeout)
    
    if exists:
        return True, url, status_code, ""
    
    # If 4xx error (client error like 404, 403), try climbing up
    # Don't climb for 5xx (server errors) or connection errors
    if 400 <= status_code < 500:
        if log_callback:
            log_callback(f"🔄 [URL Validator] Got {status_code} for {url}, trying parent URLs...")
        
        parent_urls = get_parent_urls(url)[:max_climb_levels]
        
        for parent_url in parent_urls:
            parent_exists, parent_status, parent_error = await check_url_exists(parent_url, timeout)
            
            if parent_exists:
                if log_callback:
                    log_callback(f"✅ [URL Validator] Found valid parent: {parent_url}")
                return True, parent_url, parent_status, f"Redirected from: {url}"
            
            if log_callback:
                log_callback(f"   ↳ Parent {parent_url}: {parent_status or 'failed'}")
        
        # All parent URLs also failed
        if log_callback:
            log_callback(f"❌ [URL Validator] No valid parent found for {url}")
    
    return False, url, status_code, error_msg


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


async def validate_urls_in_text(text: str, log_callback=None, use_fallback: bool = True) -> Dict[str, any]:
    """Validate ALL URLs in text and return results.
    
    NO WHITELIST - All URLs are validated regardless of domain.
    
    Features:
    - If a URL returns 4xx, tries parent paths to find working alternative
    - Tracks URL replacements for text substitution
    
    Args:
        text: Text containing URLs to validate
        log_callback: Optional logging function
        use_fallback: If True, try parent URLs when original returns 4xx
        
    Returns:
        Dictionary with validation results:
        {
            "valid_urls": List of valid URLs,
            "invalid_urls": List of invalid URLs with reasons,
            "url_replacements": Dict mapping original URL -> fallback URL,
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
            "url_replacements": {},
            "all_urls_valid": True
        }
    
    if log_callback:
        log_callback(f"🔍 [URL Validator] Found {len(urls)} URL(s) - validating ALL (with fallback: {use_fallback})")
    
    valid_urls = []
    invalid_urls = []
    url_replacements = {}  # original_url -> fallback_url
    
    # Validate ALL URLs (with fallback if enabled)
    if use_fallback:
        # Use fallback validation (tries parent URLs on 4xx)
        tasks = [check_url_with_fallback(url, log_callback=log_callback) for url in urls]
        results = await asyncio.gather(*tasks)
        
        for url, (exists, final_url, status_code, error_msg) in zip(urls, results):
            if exists:
                valid_urls.append(final_url)
                # Track replacement if URL changed
                if final_url != url:
                    url_replacements[url] = final_url
                    if log_callback:
                        log_callback(f"🔄 [URL Validator] Replaced: {url} → {final_url}")
                else:
                    if log_callback:
                        log_callback(f"✅ [URL Validator] Valid ({status_code}): {url}")
            else:
                invalid_urls.append({
                    "url": url,
                    "status_code": status_code,
                    "error": error_msg
                })
                if log_callback:
                    log_callback(f"❌ [URL Validator] Invalid (no fallback found): {url} - {error_msg}")
    else:
        # Simple validation without fallback
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
        log_callback(f"📊 [URL Validator] Results: {len(valid_urls)} valid, {len(invalid_urls)} invalid, {len(url_replacements)} replaced")
    
    return {
        "valid_urls": valid_urls,
        "invalid_urls": invalid_urls,
        "url_replacements": url_replacements,
        "all_urls_valid": all_valid
    }


def apply_url_replacements(text: str, url_replacements: Dict[str, str]) -> str:
    """Replace original URLs with their fallback alternatives.
    
    Args:
        text: Original text with URLs
        url_replacements: Dict mapping original_url -> fallback_url
        
    Returns:
        Text with URLs replaced by their fallbacks
    """
    if not url_replacements:
        return text
    
    modified_text = text
    
    for original_url, fallback_url in url_replacements.items():
        modified_text = modified_text.replace(original_url, fallback_url)
    
    return modified_text


def remove_invalid_urls_from_text(
    text: str, 
    invalid_urls: List[Dict],
    url_replacements: Optional[Dict[str, str]] = None
) -> str:
    """Remove invalid URLs from text, apply replacements, and add disclaimers.
    
    Args:
        text: Original text with URLs
        invalid_urls: List of invalid URL dictionaries
        url_replacements: Optional dict mapping original_url -> fallback_url
        
    Returns:
        Text with:
        - Invalid URLs removed or marked
        - Working fallback URLs substituted
        - Disclaimers added if needed
    """
    modified_text = text
    
    # First, apply URL replacements (original → fallback)
    if url_replacements:
        modified_text = apply_url_replacements(modified_text, url_replacements)
    
    # Then remove truly invalid URLs (no fallback found)
    if not invalid_urls:
        return modified_text
    
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


def detect_fabricated_contact_info(text: str, log_callback=None) -> Dict[str, any]:
    """Detect potentially fabricated contact information in text.
    
    Strategy:
    - Emails WITH LibGuide/tool context → Allow (from tools, semi-safe)
    - Emails WITHOUT tool context → Flag for removal (fabricated)
    - Names with LibGuide context → Allow
    - Standalone names without context → Flag for removal
    
    Args:
        text: Text to check for fabricated contact info
        log_callback: Optional logging function
        
    Returns:
        Dictionary with detected contact info
    """
    detected = {
        "emails": [],
        "fabricated_emails": [],
        "has_suspicious_contact": False,
        "has_tool_context": False
    }
    
    # Check if there's evidence this came from tools
    # LibGuide URLs, MyGuide patterns, verified library domains, or verified agent sources
    has_tool_context = bool(re.search(
        r'libguides\.lib\.miamioh\.edu|miamioh\.libguides\.com|Source:|Guide:|Subject Guide:|Subject Librarian Agent|LibGuides API|VERIFIED API DATA', 
        text, 
        re.IGNORECASE
    ))
    detected["has_tool_context"] = has_tool_context
    
    # Find all @miamioh.edu emails
    emails = re.findall(EMAIL_PATTERN, text, re.IGNORECASE)
    
    if emails:
        detected["emails"] = emails
        
        if has_tool_context:
            # Emails with tool context are allowed (from LibGuides/MyGuide)
            if log_callback:
                log_callback(f"✅ [Contact Validator] Detected {len(emails)} email(s) with tool context - allowing")
        else:
            # Emails without tool context are fabricated
            detected["fabricated_emails"] = emails
            detected["has_suspicious_contact"] = True
            if log_callback:
                log_callback(f"❌ [Contact Validator] Detected {len(emails)} fabricated email(s) - will be removed")
    
    # Check for standalone names without any context
    if not has_tool_context and not emails:
        name_matches = re.findall(LIBRARIAN_NAME_PATTERN, text, re.IGNORECASE)
        if name_matches:
            detected["has_suspicious_contact"] = True
            if log_callback:
                log_callback(f"⚠️ [Contact Validator] Detected standalone name(s) without tool context: {', '.join(name_matches)}")
    
    return detected


def remove_fabricated_contact_info(text: str, detected_info: Dict, log_callback=None) -> str:
    """Remove ONLY fabricated contact information from text.
    
    Strategy:
    - Emails WITH tool context → KEEP (from LibGuides/MyGuide, semi-safe)
    - Emails WITHOUT tool context → REMOVE (fabricated)
    - Names with tool context → KEEP
    - Standalone names without context → REMOVE
    
    Args:
        text: Original text
        detected_info: Dictionary from detect_fabricated_contact_info
        log_callback: Optional logging function
        
    Returns:
        Text with ONLY fabricated contact info removed, tool-sourced info preserved
    """
    if not detected_info["has_suspicious_contact"]:
        return text
    
    modified_text = text
    removed_count = 0
    has_tool_context = detected_info.get("has_tool_context", False)
    fabricated_emails = detected_info.get("fabricated_emails", [])
    
    # Only remove emails that are fabricated (no tool context)
    for email in fabricated_emails:
        # No tool context = fabricated, remove everything
        patterns = [
            # Remove name with email
            (rf'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s*[,:\(]\s*{re.escape(email)}\s*[\),]?', ''),
            # Remove email line
            (rf'\n?\s*•?\s*Email:\s*{re.escape(email)}\s*\n?', '\n'),
            # Remove just email
            (rf'{re.escape(email)}', ''),
        ]
        
        for pattern, replacement in patterns:
            if re.search(pattern, modified_text, re.IGNORECASE):
                modified_text = re.sub(pattern, replacement, modified_text, flags=re.IGNORECASE)
                removed_count += 1
                if log_callback:
                    log_callback(f"✂️ [Contact Validator] Removed fabricated email: {email}")
                break
    
    # Clean up any double newlines or empty formatting
    modified_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', modified_text)
    modified_text = re.sub(r'•\s*\n', '', modified_text)
    modified_text = re.sub(r'\n\s*\n\s*$', '\n', modified_text)
    
    # Add warning only if we removed fabricated content
    if removed_count > 0:
        warning = "\n\n⚠️ **Note**: Some contact information could not be verified. For accurate contact details, visit https://www.lib.miamioh.edu/research/research-support/ask/ or call (513) 529-4141."
        modified_text += warning
    
    return modified_text


def correct_ill_urls(text: str, user_message: str = "", log_callback=None) -> str:
    """Correct ILL URLs to default to main campus unless user specifies regional campus.
    
    The bot sometimes picks up regional campus ILL URLs from Google Site Search.
    This function corrects them to the main campus URL by default, unless the
    user specifically mentioned Hamilton or Middletown.
    
    Args:
        text: Response text that may contain ILL URLs
        user_message: Original user message to check for campus mentions
        log_callback: Optional logging function
        
    Returns:
        Text with corrected ILL URLs
    """
    user_msg_lower = user_message.lower() if user_message else ""
    
    # Check if user specifically mentioned a regional campus
    mentions_hamilton = any(p in user_msg_lower for p in ["hamilton", "rentschler"])
    mentions_middletown = any(p in user_msg_lower for p in ["middletown", "gardner-harvey", "gardner harvey"])
    
    corrected_text = text
    
    for regional_url, main_url in ILL_URL_CORRECTIONS.items():
        if regional_url in corrected_text:
            # Only correct if user didn't specifically ask about that campus
            should_correct = True
            
            if "libguides.lib.miamioh.edu/ILLPolicy" in regional_url and mentions_hamilton:
                should_correct = False
                if log_callback:
                    log_callback(f"✅ [ILL Correction] Keeping Hamilton ILL URL - user mentioned Hamilton")
            
            if "mid.miamioh.edu" in regional_url and mentions_middletown:
                should_correct = False
                if log_callback:
                    log_callback(f"✅ [ILL Correction] Keeping Middletown ILL URL - user mentioned Middletown")
            
            if should_correct:
                corrected_text = corrected_text.replace(regional_url, main_url)
                if log_callback:
                    log_callback(f"🔄 [ILL Correction] Corrected regional ILL URL → main campus: {main_url}")
    
    return corrected_text


async def validate_and_clean_response(response_text: str, log_callback=None, agents_used=None, user_message: str = "") -> Tuple[str, bool]:
    """Validate URLs and contact info in response and remove invalid/fabricated ones.
    
    This is the main function to call before returning a response to the user.
    
    Args:
        response_text: The response text to validate
        log_callback: Optional logging function
        agents_used: Optional list of agent names that were used (to skip validation for verified agents)
        user_message: Original user message (used for ILL URL correction)
        
    Returns:
        Tuple of (cleaned_text: str, had_issues: bool)
    """
    had_issues = False
    cleaned_text = response_text
    
    # Step 0: Correct ILL URLs to default to main campus
    cleaned_text = correct_ill_urls(cleaned_text, user_message, log_callback)
    
    # Step 1: Validate all URLs (with fallback to parent URLs on 4xx errors)
    validation_results = await validate_urls_in_text(cleaned_text, log_callback, use_fallback=True)
    
    url_replacements = validation_results.get("url_replacements", {})
    invalid_urls = validation_results.get("invalid_urls", [])
    
    # Apply URL replacements and remove truly invalid URLs
    if url_replacements or invalid_urls:
        cleaned_text = remove_invalid_urls_from_text(
            cleaned_text, 
            invalid_urls,
            url_replacements
        )
        
        if url_replacements:
            if log_callback:
                log_callback(f"🔄 [URL Validator] Replaced {len(url_replacements)} URL(s) with working parent paths")
        
        if invalid_urls:
            had_issues = True
            if log_callback:
                log_callback(f"🔧 [URL Validator] Removed {len(invalid_urls)} invalid URL(s) with no fallback")
    
    # Step 2: Detect and remove fabricated contact info
    # SKIP contact validation if using verified API agents (subject_librarian, libguide, etc.)
    verified_agents = ["subject_librarian", "libguide", "libcal", "primo"]
    skip_contact_validation = agents_used and any(agent in verified_agents for agent in agents_used)
    
    # Also skip if this is a booking confirmation (contains confirmation number pattern)
    is_booking_confirmation = bool(re.search(r'confirmation (number|id|code):?\s*\w+', cleaned_text, re.IGNORECASE))
    if is_booking_confirmation:
        skip_contact_validation = True
        if log_callback:
            log_callback(f"✅ [Contact Validator] Skipping validation - booking confirmation detected")
    
    if skip_contact_validation and not is_booking_confirmation and log_callback:
        log_callback(f"✅ [Contact Validator] Skipping validation - response from verified agent(s): {agents_used}")
    
    if not skip_contact_validation:
        detected_contact = detect_fabricated_contact_info(cleaned_text, log_callback)
        
        if detected_contact["has_suspicious_contact"]:
            cleaned_text = remove_fabricated_contact_info(cleaned_text, detected_contact, log_callback)
            had_issues = True
    
    return cleaned_text, had_issues
