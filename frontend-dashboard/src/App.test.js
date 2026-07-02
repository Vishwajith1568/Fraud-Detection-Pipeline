import { render, screen } from '@testing-library/react';
import App from './App';

test('renders login screen when not authenticated', () => {
  // Clear any stored token
  localStorage.removeItem('token');
  render(<App />);
  const loginHeading = screen.getByText(/Security Command Login/i);
  expect(loginHeading).toBeInTheDocument();
});

test('renders authenticate button', () => {
  localStorage.removeItem('token');
  render(<App />);
  const button = screen.getByText(/Authenticate Session/i);
  expect(button).toBeInTheDocument();
});