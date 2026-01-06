/**
 * ClarifyChips Component
 * 
 * Displays clarification question with button options when the router
 * needs user input to disambiguate their query.
 * 
 * Uses shadcn/ui Button and Card components for modern UI.
 */

import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { HelpCircle, Loader2 } from 'lucide-react';

export function ClarifyChips({ 
  question, 
  options, 
  onSelect,
  disabled = false 
}) {
  const [selectedValue, setSelectedValue] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSelect = async (value) => {
    if (disabled || isSubmitting) return;

    setSelectedValue(value);
    setIsSubmitting(true);

    try {
      await onSelect(value);
    } catch (error) {
      console.error('Error submitting clarification:', error);
      setIsSubmitting(false);
      setSelectedValue(null);
    }
  };

  return (
    <Card className="border-blue-200 bg-blue-50/50">
      <CardHeader>
        <div className="flex items-start gap-3">
          <HelpCircle className="h-5 w-5 text-blue-600 mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <CardTitle className="text-base font-semibold text-blue-900">
              {question}
            </CardTitle>
            <CardDescription className="text-sm text-blue-700 mt-1">
              Please select the option that best matches what you're looking for
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      
      <CardContent>
        <div className="grid gap-2">
          {options.map((option, index) => {
            const isSelected = selectedValue === option.value;
            const isOtherOption = option.value === 'other';
            
            return (
              <Button
                key={option.value || index}
                variant={isOtherOption ? "outline" : "default"}
                className={`
                  w-full justify-start text-left h-auto py-3 px-4
                  ${isSelected ? 'opacity-50 cursor-not-allowed' : ''}
                  ${isOtherOption ? 'border-gray-300 text-gray-700 hover:bg-gray-50' : ''}
                  ${!isOtherOption && !isSelected ? 'bg-blue-600 hover:bg-blue-700 text-white' : ''}
                `}
                onClick={() => handleSelect(option.value)}
                disabled={disabled || isSubmitting}
              >
                <div className="flex items-center gap-2 w-full">
                  {isSubmitting && isSelected && (
                    <Loader2 className="h-4 w-4 animate-spin flex-shrink-0" />
                  )}
                  <div className="flex-1">
                    <div className="font-medium">
                      {option.label}
                    </div>
                    {option.description && (
                      <div className={`text-xs mt-0.5 ${isOtherOption ? 'text-gray-500' : 'text-blue-100'}`}>
                        {option.description}
                      </div>
                    )}
                  </div>
                </div>
              </Button>
            );
          })}
        </div>

        {isSubmitting && (
          <Alert className="mt-4 border-blue-200 bg-blue-50">
            <Loader2 className="h-4 w-4 animate-spin" />
            <AlertDescription className="text-blue-900">
              Processing your selection...
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}

export default ClarifyChips;
