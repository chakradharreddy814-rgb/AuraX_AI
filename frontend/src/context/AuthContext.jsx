import { createContext, useContext, useState, useCallback } from 'react';
import { api } from '../lib/api';

const AuthContext = createContext(null);

const TOKEN_KEY = 'aurax_token';
const COMPANY_KEY = 'aurax_company';

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [company, setCompany] = useState(() => {
    const raw = localStorage.getItem(COMPANY_KEY);
    return raw ? JSON.parse(raw) : null;
  });

  const login = useCallback(async (email, password) => {
    const data = await api.login({ email, password });
    localStorage.setItem(TOKEN_KEY, data.token);
    const companyInfo = { company_id: data.company_id, company_name: data.company_name };
    localStorage.setItem(COMPANY_KEY, JSON.stringify(companyInfo));
    setToken(data.token);
    setCompany(companyInfo);
    return data;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(COMPANY_KEY);
    setToken(null);
    setCompany(null);
  }, []);

  const updateCompany = useCallback((companyInfo) => {
    const nextCompany = {
      company_id: companyInfo.company_id,
      company_name: companyInfo.company_name,
      full_name: companyInfo.full_name,
      company_logo_url: companyInfo.company_logo_url,
      email: companyInfo.email,
    };
    localStorage.setItem(COMPANY_KEY, JSON.stringify(nextCompany));
    setCompany(nextCompany);
  }, []);

  const refreshCompany = useCallback(async () => {
    const data = await api.me();
    updateCompany(data);
    return data;
  }, [updateCompany]);

  const value = {
    token,
    company,
    isAuthenticated: !!token,
    login,
    logout,
    updateCompany,
    refreshCompany,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
