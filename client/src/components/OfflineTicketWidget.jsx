import { useState, useContext } from 'react';
import { SocketContext } from '../context/SocketContextProvider';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const OfflineTicketWidget = () => {
  const [question, setQuestion] = useState('');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [details, setDetails] = useState('');

  const { socketContextValues } = useContext(SocketContext);

  const handleTicketSubmit = (e) => {
    e.preventDefault();
    const formData = new FormData();
    formData.append('question', question);
    formData.append('email', email);
    formData.append('name', name);
    formData.append('details', details);
    formData.append('ua', navigator.userAgent);
    socketContextValues.offlineTicketSubmit(formData);
  };

  return (
    <form onSubmit={handleTicketSubmit} className="space-y-4">
      <div>
        <Label>Name</Label>
        <Input
          placeholder="Enter your name..."
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1"
        />
      </div>
      <div>
        <Label>Question</Label>
        <Input
          placeholder="Enter your question..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          className="mt-1"
        />
      </div>
      <div>
        <Label>Details</Label>
        <Input
          placeholder="Enter details about your question..."
          value={details}
          onChange={(e) => setDetails(e.target.value)}
          className="mt-1"
        />
      </div>
      <div>
        <Label>Email</Label>
        <Input
          placeholder="Enter your email..."
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1"
        />
      </div>
      <Button type="submit" variant="miami" className="mt-2">
        Submit
      </Button>
    </form>
  );
};

export default OfflineTicketWidget;
