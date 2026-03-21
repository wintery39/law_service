import { BrowserRouter } from 'react-router-dom';
import { ToastProvider } from './context/ToastContext';
import { AppRoutes } from './app/router';

export default function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </ToastProvider>
  );
}
