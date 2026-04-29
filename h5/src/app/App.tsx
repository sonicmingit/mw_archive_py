import { useEffect } from 'react';
import { RouterProvider } from 'react-router';
import { router } from './routes';
import { initTheme } from './lib/theme';

export default function App() {
  useEffect(() => {
    initTheme();
  }, []);

  return <RouterProvider router={router} />;
}
