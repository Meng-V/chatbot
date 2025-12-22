# Smart Clarification System

**Last Updated:** December 22, 2025  
**Version:** 3.1.0

---

## Table of Contents
1. [Overview](#overview)
2. [How It Works](#how-it-works)
3. [Implementation Details](#implementation-details)
4. [Frontend Integration](#frontend-integration)
5. [Backend Processing](#backend-processing)
6. [Testing](#testing)
7. [Customization](#customization)

---

## Overview

The **Smart Clarification System** is a user-in-the-loop feature that presents interactive button choices when the bot cannot confidently classify a user's question. This improves accuracy by letting users confirm their intent before the bot processes the query.

### Key Features

- **RAG-Based Classification** - Uses Weaviate vector database for intent classification with confidence scoring
- **Margin-Based Ambiguity Detection** - Triggers clarification when top-2 categories are too close
- **Interactive Button UI** - Clean, accessible buttons using shadcn components
- **"None of the above" Option** - Allows users to provide more context for edge cases
- **Reclassification** - Enhanced processing with additional user-provided details

### When Clarification Triggers

Clarification choices appear when:
1. **Low margin**: `(top_score - second_score) / top_score < 0.15`
2. **Small score difference**: `top_score - second_score < 0.3`
3. **Both conditions met** - Indicates genuine ambiguity

---

## How It Works

### User Flow

```
1. User asks ambiguous question
   Example: "I need help with a computer"
        ↓
2. RAG Classifier detects low confidence
   Top-1: library_equipment_checkout (0.650)
   Top-2: out_of_scope_tech_support (0.620)
   Margin: 0.046 (< 0.15 threshold)
        ↓
3. Bot generates clarification choices
   - Choice 1: Borrow equipment (laptops, chargers)
   - Choice 2: Get help with broken computer
   - Choice 3: None of the above
        ↓
4a. User clicks specific category button
    → Bot continues with confirmed intent
    → Processes question normally
        ↓
4b. User clicks "None of the above"
    → Bot asks for more details
    → User types additional context
    → Bot reclassifies with enhanced query
        ↓
5. Bot provides accurate, relevant answer
```

### Example Interaction

**User:** "I need help with a computer"

**Bot:** 
> I want to make sure I understand your question correctly. Which of these best describes what you're looking for?
> 
> [Button] **Borrow equipment (laptops, chargers, etc.)**  
> Questions about borrowing library equipment
> 
> [Button] **Get help with a broken computer**  
> Technical problems with computers or devices
> 
> [Button] **None of the above**  
> My question is about something else

**User:** [Clicks "Borrow equipment"]

**Bot:** 
> Here's how to borrow equipment from the library:
> 
> King Library offers laptop and charger loans at the Circulation Desk...

---

## Implementation Details

### Backend Components

#### 1. RAG Classifier (`src/classification/rag_classifier.py`)

**Function:** `classify_with_rag(question, logger)`

Classifies user questions and detects ambiguity:

```python
# Returns classification result
{
    "category": "library_equipment_checkout",
    "confidence": 0.650,
    "needs_clarification": True,
    "clarification_choices": {
        "original_question": "I need help with a computer",
        "choices": [
            {
                "id": "choice_0",
                "label": "Borrow equipment (laptops, chargers, etc.)",
                "description": "Questions about borrowing library equipment",
                "category": "library_equipment_checkout",
                "examples": ["How to borrow a laptop", "Checkout chargers"]
            },
            {
                "id": "choice_1", 
                "label": "Get help with a broken computer",
                "description": "Technical problems with computers or devices",
                "category": "out_of_scope_tech_support",
                "examples": ["My computer won't turn on", "WiFi not working"]
            },
            {
                "id": "none",
                "label": "None of the above",
                "description": "My question is about something else"
            }
        ]
    }
}
```

**Key Methods:**
- `_generate_clarification_choices()` - Creates structured choice objects
- `_generate_choice_label()` - User-friendly labels for categories
- Margin calculation: `(top_score - second_score) / top_score`

#### 2. Clarification Handler (`src/classification/clarification_handler.py`)

**Function:** `handle_clarification_choice(choice_id, original_question, clarification_data, logger)`

Processes user's button selection:

```python
async def handle_clarification_choice(choice_id, original_question, clarification_data, logger):
    if choice_id == "none":
        # User selected "None of the above"
        return {
            "needs_more_info": True,
            "response_message": "Could you please provide more details about your question?"
        }
    else:
        # User selected specific category
        selected_choice = find_choice_by_id(choice_id, clarification_data)
        return {
            "needs_more_info": False,
            "confirmed_category": selected_choice["category"],
            "confirmed_label": selected_choice["label"]
        }
```

**Function:** `reclassify_with_additional_context(original_question, additional_details, conversation_history, logger)`

Reclassifies with enhanced context when user provides more details.

#### 3. Socket.IO Handlers (`src/main.py`)

**Event:** `clarificationChoice`

Handles button click from frontend:

```python
@sio.event
async def clarificationChoice(sid, data):
    choice_id = data.get("choiceId")
    original_question = data.get("originalQuestion")
    clarification_data = data.get("clarificationData")
    
    result = await handle_clarification_choice(...)
    
    if result.get("needs_more_info"):
        await sio.emit("requestMoreDetails", {...})
    else:
        # Continue processing with confirmed category
        await route_query(enhanced_question, ...)
```

**Event:** `provideMoreDetails`

Handles additional context from user:

```python
@sio.event
async def provideMoreDetails(sid, data):
    original_question = data.get("originalQuestion")
    additional_details = data.get("additionalDetails")
    
    # Reclassify with enhanced context
    enhanced_question = f"{original_question}. {additional_details}"
    final_result = await route_query(enhanced_question, ...)
```

#### 4. Hybrid Router Pre-Check (`src/graph/hybrid_router_rag.py`)

Pre-checks for specific patterns (e.g., address queries) before classification to ensure correct routing.

---

## Frontend Integration

### Components

#### 1. ClarificationChoices Component (`client/src/components/ClarificationChoices.jsx`)

React component that displays clarification buttons:

```jsx
<ClarificationChoices
  clarificationData={message.clarificationChoices}
  onChoiceSelect={(choice) => handleClarificationChoice(choice)}
  disabled={isTyping}
/>
```

**Features:**
- shadcn Button components with variants
- Blue buttons for category choices
- Gray outline button for "None of the above"
- Disabled state during processing
- Accessible keyboard navigation

#### 2. ChatBotComponent Integration (`client/src/components/ChatBotComponent.jsx`)

**Handler Functions:**

```javascript
const handleClarificationChoice = useCallback((choice, originalQuestion, clarificationData) => {
  socket.emit('clarificationChoice', {
    choiceId: choice.id,
    originalQuestion: originalQuestion,
    clarificationData: clarificationData
  });
}, [socket]);

const handleProvideMoreDetails = useCallback((originalQuestion, additionalDetails) => {
  socket.emit('provideMoreDetails', {
    originalQuestion: originalQuestion,
    additionalDetails: additionalDetails
  });
}, [socket]);
```

**Event Listeners:**

```javascript
useEffect(() => {
  socket.on('requestMoreDetails', (data) => {
    setShowDetailsInput(true);
    setPendingOriginalQuestion(data.originalQuestion);
    messageContextValues.addMessage(data.message, 'bot');
  });
}, [socket]);
```

**Conditional Input:**

```jsx
{showDetailsInput ? (
  <form onSubmit={handleSubmitDetails}>
    <Input placeholder="Please provide more details..." />
    <Button>Send Details</Button>
  </form>
) : (
  <form onSubmit={handleFormSubmit}>
    <Input placeholder="Type your message..." />
    <Button>Send</Button>
  </form>
)}
```

---

## Backend Processing

### Classification Flow

```python
# 1. User message received
user_message = "I need help with a computer"

# 2. RAG classification
classification = await classify_with_rag(user_message, logger)

# 3. Check if clarification needed
if classification.get("needs_clarification"):
    clarification_choices = classification.get("clarification_choices")
    
    # 4. Send clarification choices to frontend
    response_data = {
        "message": "I want to make sure I understand...",
        "clarificationChoices": clarification_choices
    }
    await sio.emit("message", response_data)
    
    # 5. Wait for user selection...
    # (Handled by clarificationChoice event)
```

### Choice Processing Flow

```python
# 1. User selects choice
choice_id = "choice_0"  # Selected "Borrow equipment"

# 2. Handle selection
result = await handle_clarification_choice(choice_id, original_question, clarification_data)

# 3. If specific category selected
if not result.get("needs_more_info"):
    confirmed_category = result.get("confirmed_category")
    
    # 4. Enhanced question with category hint
    enhanced_question = f"{original_question} [User confirmed: {confirmed_category}]"
    
    # 5. Route with confirmed intent
    final_result = await route_query(enhanced_question, logger, history)
    
    # 6. Send final answer
    await sio.emit("message", {
        "message": final_result.get("final_answer"),
        "clarification_resolved": True
    })
```

### Reclassification Flow

```python
# 1. User clicks "None of the above"
# Backend emits "requestMoreDetails"

# 2. User provides additional details
additional_details = "I want to use a computer to study in the library"

# 3. Reclassify with enhanced context
enhanced_question = f"{original_question}. {additional_details}"
classification_result = await reclassify_with_additional_context(
    original_question,
    additional_details,
    conversation_history
)

# 4. Process with new classification
final_result = await route_query(enhanced_question, logger, history)
```

---

## Testing

### Mock Tests (No Weaviate Required)

**Script:** `ai-core/scripts/test_clarification_mock.py`

Tests clarification handling logic without external dependencies:

```bash
cd ai-core
source .venv/bin/activate
python3 scripts/test_clarification_mock.py
```

**Tests:**
1. Clarification choice generation
2. Specific category selection
3. "None of the above" handling
4. Reclassification with context
5. Edge cases

### Integration Tests (Requires Weaviate)

**Script:** `ai-core/scripts/test_clarification_choices.py`

End-to-end tests with real RAG classification:

```bash
cd ai-core
source .venv/bin/activate
python3 scripts/test_clarification_choices.py
```

**Tests:**
1. Ambiguous question detection
2. Clarification choice structure
3. User choice selection flow
4. Reclassification accuracy
5. Multiple clarifications in conversation

### Manual Testing

**Test Questions:**
- "I need help with a computer"
- "Can you help me with printing?"
- "I have a question about books"
- "Where can I study?"

**Expected Behavior:**
1. Bot shows 2-3 category buttons + "None of the above"
2. Buttons are clickable and responsive
3. Clicking specific category continues conversation
4. Clicking "None of the above" prompts for details
5. Providing details reclassifies correctly

---

## Customization

### Adjusting Clarification Thresholds

**File:** `src/classification/rag_classifier.py`

```python
# Current thresholds
MARGIN_THRESHOLD = 0.15  # Low margin triggers clarification
SCORE_DIFF_THRESHOLD = 0.3  # Small difference triggers clarification

# To make clarification MORE sensitive (more frequent):
MARGIN_THRESHOLD = 0.20  # Higher = more clarifications
SCORE_DIFF_THRESHOLD = 0.4

# To make clarification LESS sensitive (less frequent):
MARGIN_THRESHOLD = 0.10  # Lower = fewer clarifications
SCORE_DIFF_THRESHOLD = 0.2
```

### Adding Category Labels

**File:** `src/classification/rag_classifier.py`

```python
def _generate_choice_label(self, category, examples):
    label_map = {
        "library_equipment_checkout": "Borrow equipment (laptops, chargers, etc.)",
        "library_hours_rooms": "Library hours or room reservations",
        "subject_librarian_guides": "Find a subject librarian or research guide",
        # Add your custom labels here
        "your_category": "Your Custom Label",
    }
    return label_map.get(category, category.replace("_", " ").title())
```

### Customizing UI Appearance

**File:** `client/src/components/ClarificationChoices.jsx`

```jsx
// Button variant for category choices
<Button
  variant="default"  // Change to "outline", "secondary", etc.
  size="lg"         // Change to "sm", "md", "lg"
  className="justify-start text-left"  // Custom Tailwind classes
>
```

### Changing Prompt Text

**Frontend:** `client/src/components/ClarificationChoices.jsx`

```jsx
const promptText = "I want to make sure I understand your question correctly. Which of these best describes what you're looking for?"
```

**Backend:** `src/classification/clarification_handler.py`

```python
response_message = "Could you please provide more details about your question? This will help me understand better."
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│                  User Frontend                  │
│  - Displays clarification buttons              │
│  - Handles button clicks                       │
│  - Shows additional details input              │
└────────────────┬────────────────────────────────┘
                 │ Socket.IO Events
                 │
┌────────────────▼────────────────────────────────┐
│              Backend Server                     │
│  ┌──────────────────────────────────────────┐  │
│  │     RAG Classifier (Weaviate)            │  │
│  │  - Confidence scoring                    │  │
│  │  - Margin-based ambiguity detection      │  │
│  │  - Generate clarification choices        │  │
│  └──────────────┬───────────────────────────┘  │
│                 │                               │
│  ┌──────────────▼───────────────────────────┐  │
│  │     Clarification Handler                │  │
│  │  - Process user choice selection         │  │
│  │  - Handle "None of the above"            │  │
│  │  - Reclassify with additional context    │  │
│  └──────────────┬───────────────────────────┘  │
│                 │                               │
│  ┌──────────────▼───────────────────────────┐  │
│  │     Socket.IO Handlers                   │  │
│  │  - clarificationChoice event             │  │
│  │  - provideMoreDetails event              │  │
│  │  - requestMoreDetails emission           │  │
│  └──────────────┬───────────────────────────┘  │
│                 │                               │
│  ┌──────────────▼───────────────────────────┐  │
│  │     Query Router                         │  │
│  │  - Route with confirmed intent           │  │
│  │  - Process final answer                  │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

---

## Troubleshooting

### Clarification Not Appearing

**Check:**
1. RAG classification returning confidence scores
2. Margin and score difference thresholds
3. Frontend receiving `clarificationChoices` in message data
4. Console logs for classification results

**Debug:**
```python
# In rag_classifier.py, add logging
logger.log(f"Margin: {margin:.3f}, Score diff: {score_diff:.3f}")
logger.log(f"Needs clarification: {needs_clarification}")
```

### Button Clicks Not Working

**Check:**
1. Socket.IO connection established
2. `clarificationChoice` event handler registered
3. Browser console for JavaScript errors
4. Backend receiving choice selection

**Debug:**
```javascript
// In ChatBotComponent.jsx
console.log('Emitting clarificationChoice:', {
  choiceId: choice.id,
  originalQuestion: originalQuestion
});
```

### "None of the above" Not Prompting

**Check:**
1. `requestMoreDetails` event listener registered
2. `showDetailsInput` state updating correctly
3. Backend emitting `requestMoreDetails` event
4. Input field rendering conditionally

---

## Performance Considerations

### Response Time Impact

- **With clarification**: +1-2 seconds (waiting for user choice)
- **Without clarification**: Normal processing time
- **Benefit**: Higher accuracy, fewer follow-up questions

### Optimization Tips

1. **Cache classification results** - Avoid re-classifying same questions
2. **Limit choice count** - Maximum 3 category choices for clarity
3. **Pre-check patterns** - Use regex for obvious categories (e.g., address queries)
4. **Batch similar queries** - Group related questions in clarification choices

---

## Future Enhancements

**Potential improvements:**
- [ ] Remember user preferences for recurring ambiguous patterns
- [ ] Multi-level clarification (subcategories)
- [ ] Confidence threshold learning based on user feedback
- [ ] Analytics dashboard for clarification metrics
- [ ] A/B testing different clarification prompts

---

## Related Documentation

- **[RAG Classification System](./05-WEAVIATE-RAG-CORRECTION-POOL.md)** - Weaviate setup and classification examples
- **[System Overview](./01-SYSTEM-OVERVIEW.md)** - Architecture and agent system
- **[Frontend Development](../client/README.md)** - React components and Socket.IO

---

**Document Version:** 3.1.0  
**Last Updated:** December 22, 2025  
**Feature Status:** Production Ready ✅
