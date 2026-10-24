import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';
import { authApi, tokenStorage, getApiError } from '../lib/api';

interface AuthContextValue {
  isAuthenticated: boolean;
  isLoading: boolean;
  userEmail: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, businessName: string) => Promise<void>;
  logout: () => void;
}

const EMAIL_KEY = 'nf_user_email';

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(
    () => tokenStorage.get() !== null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [userEmail, setUserEmail] = useState<string | null>(
    () => localStorage.getItem(EMAIL_KEY),
  );

  const logout = useCallback(() => {
    tokenStorage.clear();
    localStorage.removeItem(EMAIL_KEY);
    setIsAuthenticated(false);
    setUserEmail(null);
  }, []);

  // Listen for session-expired events from the API interceptor
  useEffect(() => {
    const handler = () => logout();
    window.addEventListener('nf:session-expired', handler);
    return () => window.removeEventListener('nf:session-expired', handler);
  }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const response = await authApi.login(email, password);
      tokenStorage.set(response.access_token);
      localStorage.setItem(EMAIL_KEY, email);
      setIsAuthenticated(true);
      setUserEmail(email);
    } catch (err) {
      throw new Error(getApiError(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const register = useCallback(
    async (email: string, password: string, businessName: string) => {
      setIsLoading(true);
      try {
        await authApi.register(email, password, businessName);
        // After registration, auto-login
        const response = await authApi.login(email, password);
        tokenStorage.set(response.access_token);
        localStorage.setItem(EMAIL_KEY, email);
        setIsAuthenticated(true);
        setUserEmail(email);
      } catch (err) {
        throw new Error(getApiError(err));
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  return (
    <AuthContext.Provider
      value={{ isAuthenticated, isLoading, userEmail, login, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
