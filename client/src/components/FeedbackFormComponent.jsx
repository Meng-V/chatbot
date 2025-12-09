import { useContext, useState } from 'react';
import { Star } from 'lucide-react';
import { SocketContext } from '../context/SocketContextProvider';
import { MessageContext } from '../context/MessageContextProvider';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';

const FeedbackFormComponent = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [hover, setHover] = useState(null);
  const [rating, setRating] = useState(0);
  const [details, setDetails] = useState(undefined);
  const { socketContextValues } = useContext(SocketContext);
  const { messageContextValues } = useContext(MessageContext);

  const handleFormOpen = () => {
    setIsOpen(true);
    setHover(null);
  };

  const handleRating = (curRating) => {
    setRating(curRating);
  };

  const handleFormSubmit = () => {
    socketContextValues.sendUserFeedback({
      userRating: rating,
      userComment: details,
    });
    setRating(0);
    setDetails(undefined);
    setHover(null);
    setIsOpen(false);
  };

  return (
    <>
      <Button
        disabled={messageContextValues.message.length < 3}
        onClick={handleFormOpen}
        size="xs"
        variant="secondary"
        className="mr-[7%]"
      >
        Rate this conversation
      </Button>
      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent>
          <DialogHeader className="flex flex-row items-center ps-2">
            <img
              src="https://libapps.s3.amazonaws.com/accounts/190074/images/0721_STier1_Libraries_HS_186KW_K_Digital.png"
              height={50}
              width={120}
              alt="library logo"
            />
            <DialogTitle className="ml-3">Smart Chatbot</DialogTitle>
          </DialogHeader>
          <form>
            <div className="space-y-4">
              <div>
                <Label>Rate this conversation</Label>
                <div className="flex gap-0.5 mt-2">
                  {[...Array(5)].map((_, index) => {
                    const ratingValue = index + 1;
                    return (
                      <label
                        key={index}
                        className="cursor-pointer"
                        onMouseEnter={() => setHover(ratingValue)}
                        onMouseLeave={() => setHover(null)}
                      >
                        <input
                          type="radio"
                          name="rating"
                          onChange={() => handleRating(ratingValue)}
                          value={ratingValue}
                          className="sr-only"
                        />
                        <Star
                          className={`h-5 w-5 transition-colors duration-200 ${
                            ratingValue <= (hover || rating)
                              ? 'fill-yellow-400 text-yellow-400'
                              : 'fill-gray-200 text-gray-200'
                          }`}
                        />
                      </label>
                    );
                  })}
                </div>
              </div>
              <div>
                <Label>Details</Label>
                <Textarea
                  placeholder="Enter details about your rating..."
                  value={details || ''}
                  onChange={(e) => setDetails(e.target.value)}
                  className="mt-2"
                />
              </div>
              <p className="text-red-500 text-sm italic">
                * Submitting this form will restart your session!
              </p>
            </div>
          </form>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setIsOpen(false)}>
              Close
            </Button>
            <Button variant="miami" onClick={handleFormSubmit}>
              Submit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default FeedbackFormComponent;
