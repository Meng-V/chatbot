import React from 'react';
import { Button } from './ui/button';
import { MessageSquare } from 'lucide-react';

/**
 * ClarificationChoices Component
 * 
 * Displays a list of clarification choices as buttons when the bot needs
 * user input to disambiguate their question.
 * 
 * @param {Object} props
 * @param {Object} props.clarificationData - Data containing prompt and choices
 * @param {Function} props.onChoiceSelect - Callback when user selects a choice
 * @param {boolean} props.disabled - Whether choices are disabled
 */
export default function ClarificationChoices({ 
  clarificationData, 
  onChoiceSelect, 
  disabled = false 
}) {
  if (!clarificationData || !clarificationData.choices) {
    return null;
  }

  const { prompt, choices } = clarificationData;

  const handleChoiceClick = (choice) => {
    if (!disabled) {
      onChoiceSelect(choice);
    }
  };

  return (
    <div className="clarification-choices-container my-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
      {/* Prompt */}
      <div className="flex items-start gap-2 mb-4">
        <MessageSquare className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" />
        <p className="text-sm text-gray-700 font-medium">
          {prompt}
        </p>
      </div>

      {/* Choice Buttons */}
      <div className="flex flex-col gap-2">
        {choices.map((choice, index) => {
          const isNoneOfAbove = choice.category === 'none_of_above';
          
          return (
            <Button
              key={choice.id}
              onClick={() => handleChoiceClick(choice)}
              disabled={disabled}
              variant={isNoneOfAbove ? 'outline' : 'default'}
              className={`
                w-full text-left justify-start h-auto py-3 px-4
                ${isNoneOfAbove 
                  ? 'border-gray-300 hover:bg-gray-100 text-gray-700' 
                  : 'bg-blue-600 hover:bg-blue-700 text-white'
                }
                ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
                transition-all duration-200
              `}
            >
              <div className="flex flex-col items-start w-full">
                {/* Label */}
                <span className="font-medium text-sm">
                  {choice.label}
                </span>
                
                {/* Description (if not "None of the above") */}
                {!isNoneOfAbove && choice.description && (
                  <span className="text-xs opacity-90 mt-1">
                    {choice.description}
                  </span>
                )}
              </div>
            </Button>
          );
        })}
      </div>

      {/* Helper text */}
      <p className="text-xs text-gray-500 mt-3 text-center">
        Click a button to continue
      </p>
    </div>
  );
}
