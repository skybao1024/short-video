import { FC, ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { PATHS } from '@/router/paths';
import { useUserStore } from '@/store/useUserStore';

interface RouteGuardProps {
  children: ReactNode;
}

const RouteGuard: FC<RouteGuardProps> = ({ children }) => {
  const { token } = useUserStore();
  const location = useLocation();

  if (!token) {
    const from = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`${PATHS.login}?from=${from}`} replace />;
  }

  return <>{children}</>;
};

export default RouteGuard;
