import React from 'react';
import { Link } from 'react-router-dom';
import { Home, AlertCircle } from 'lucide-react';

export default function NotFoundPage() {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      flexDirection: 'column',
      gap: '1.5rem',
      padding: '2rem',
      background: 'var(--color-bg-subtle)',
    }}>
      <div style={{
        width: 72, height: 72,
        borderRadius: 'var(--radius-xl)',
        background: 'var(--color-gray-100)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <AlertCircle size={32} style={{ color: 'var(--color-gray-400)' }} />
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: '4rem', fontWeight: 800, color: 'var(--color-gray-200)', lineHeight: 1 }}>404</div>
        <h1 style={{ fontSize: '1.25rem', fontWeight: 700, marginTop: '0.5rem' }}>Page not found</h1>
        <p style={{ color: 'var(--color-text-secondary)', marginTop: '0.5rem', maxWidth: 320 }}>
          The page you're looking for doesn't exist or has been moved.
        </p>
      </div>
      <Link to="/" className="btn btn-primary">
        <Home size={15} /> Go to Dashboard
      </Link>
    </div>
  );
}
