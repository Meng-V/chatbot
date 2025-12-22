# Clarification Choices System - Integration Test Guide

## ✅ Implementation Complete

All components have been implemented and integrated:

### Backend ✅
- `src/classification/rag_classifier.py` - Generates structured clarification choices
- `src/classification/clarification_handler.py` - Handles user selections
- `src/main.py` - Socket.IO handlers for `clarificationChoice` and `provideMoreDetails`

### Frontend ✅
- `client/src/components/ClarificationChoices.jsx` - Button UI component
- `client/src/components/ChatBotComponent.jsx` - Integrated with chat interface

### Tests ✅
- `scripts/test_clarification_mock.py` - All 5 tests passing
- `scripts/test_clarification_choices.py` - Full integration tests

---

## 🚀 How to Test

### Step 1: Restart Backend

```bash
cd /Users/qum/Documents/GitHub/chatbot
bash local-auto-start.sh
```

### Step 2: Test Ambiguous Questions

Ask questions that should trigger clarification choices:

**Test Questions:**
1. **"I need help with a computer"**
   - Expected: 3 choices appear:
     - Borrow equipment (laptops, chargers, etc.)
     - Get help with a broken computer
     - None of the above

2. **"I need a computer"**
   - Expected: Similar clarification choices

3. **"Can you help me with printing?"**
   - Expected: Clarification between printing services vs equipment

4. **"I have a question about books"**
   - Expected: Clarification between finding books vs borrowing policies

### Step 3: Test Choice Selection

1. **Click a specific category button**
   - Bot should continue with that category
   - No more clarification needed
   - Response should be relevant to selected category

2. **Click "None of the above"**
   - Bot asks: "Could you please provide more details..."
   - Input field changes to request details
   - Type additional context
   - Bot reclassifies with enhanced context

### Step 4: Verify End-to-End Flow

**Full Test Scenario:**

```
User: "I need help with a computer"
Bot: Shows 3 clarification buttons

User: [Clicks "Borrow equipment"]
Bot: "Here's how to borrow equipment from the library..."

---

User: "I need help with a computer"
Bot: Shows 3 clarification buttons

User: [Clicks "None of the above"]
Bot: "Could you please provide more details..."
Input: "I want to know if there are computers I can use for studying"
Bot: Provides information about using library computers
```

---

## 🔍 Expected Behavior

### Clarification Trigger Conditions

Clarification choices appear when:
- **Low margin**: `(top_score - second_score) / top_score < 0.15`
- **Small score difference**: `top_score - second_score < 0.3`
- **Boundary cases**: Known ambiguous question patterns

### UI Display

```
┌─────────────────────────────────────────────────┐
│ 💬 I want to make sure I understand your      │
│    question correctly. Which of these best    │
│    describes what you're looking for?         │
├─────────────────────────────────────────────────┤
│ [Blue Button] Borrow equipment (laptops...)    │
│   Questions about borrowing library equipment  │
│                                                 │
│ [Blue Button] Get help with broken computer    │
│   Technical problems with computers...         │
│                                                 │
│ [Gray Button] None of the above                │
│   My question is about something else          │
└─────────────────────────────────────────────────┘
```

### Backend Events

**Socket.IO Events:**
1. `message` - Initial user question
2. `message` - Bot response with `clarificationChoices` data
3. `clarificationChoice` - User clicks a button
4. `message` - Bot's final answer

**OR (if "None of the above"):**
1. `message` - Initial user question
2. `message` - Bot response with `clarificationChoices` data
3. `clarificationChoice` - User clicks "None of the above"
4. `requestMoreDetails` - Bot asks for more details
5. `provideMoreDetails` - User provides additional context
6. `message` - Bot's reclassified answer

---

## 📊 Debugging

### Check Backend Logs

Look for these log entries:

```
🎯 [RAG Classifier] Top-1: library_equipment_checkout (0.650) | 
   Top-2: out_of_scope_tech_support (0.620) | Margin: 0.046
🎯 [Clarification] User xyz123 selected choice: choice_0
✅ [Clarification Choice] Category confirmed: library_equipment_checkout
✅ [Clarification Choice] Response sent successfully
```

### Check Frontend Console

```javascript
// Should see Socket.IO events:
socket.emit('clarificationChoice', {
  choiceId: 'choice_0',
  originalQuestion: 'I need help with a computer',
  clarificationData: {...}
})
```

### Common Issues

**1. Choices Not Appearing**
- Check classification confidence/margin in logs
- Verify question triggers ambiguity threshold
- Test with known ambiguous questions

**2. Button Clicks Not Working**
- Check Socket.IO connection
- Verify `handleClarificationChoice` is called
- Check browser console for errors

**3. "None of the above" Not Prompting for Details**
- Verify `requestMoreDetails` event listener
- Check `showDetailsInput` state
- Ensure backend emits `requestMoreDetails` event

---

## 📝 Test Checklist

- [ ] Backend starts without errors
- [ ] Ambiguous question triggers clarification choices
- [ ] Clarification choices display as buttons
- [ ] Clicking specific category continues conversation
- [ ] "None of the above" prompts for more details
- [ ] Providing details reclassifies correctly
- [ ] Response is relevant to selected category
- [ ] Disabled state works during thinking
- [ ] Multiple clarifications in conversation work
- [ ] Socket.IO events fire correctly

---

## 🎯 Success Criteria

✅ User can click buttons instead of typing
✅ Bot provides 2-3 relevant choices + "None of the above"
✅ Choice selection continues conversation seamlessly  
✅ "None of the above" gracefully handles edge cases
✅ Reclassification improves accuracy with additional context
✅ UI is clear, accessible, and responsive

---

## 📚 Files Modified

### Backend
- `src/classification/rag_classifier.py` (lines 533-601)
- `src/classification/clarification_handler.py` (NEW)
- `src/main.py` (lines 440-634)

### Frontend
- `client/src/components/ClarificationChoices.jsx` (NEW)
- `client/src/components/ChatBotComponent.jsx` (updated)

### Tests
- `scripts/test_clarification_mock.py` (NEW)
- `scripts/test_clarification_choices.py` (NEW)

---

## 🎉 Next Steps

1. Start backend: `bash local-auto-start.sh`
2. Open chatbot in browser
3. Test with ambiguous questions
4. Verify button functionality
5. Test "None of the above" flow
6. Monitor backend logs for any issues

**System is ready for testing!** 🚀
