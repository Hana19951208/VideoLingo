import { BrowserRouter } from 'react-router-dom';

import { AppRouter } from './app/router';
import './styles.css';

export function App() {
  return (
    <BrowserRouter>
      <AppRouter />
    </BrowserRouter>
  );
}
