import { FC, ReactNode } from 'react';
import { Link, Outlet } from 'react-router-dom';
import styles from './index.module.scss';

interface LayoutProps {
  children?: ReactNode;
}

const Layout: FC<LayoutProps> = () => {
  return (
    <div className={styles.layout}>
      <aside className={styles.sidebar}>
        <div className={styles.logo}>V-Gen</div>
        <nav className={styles.nav}>
          <Link to="/dashboard">Video Studio</Link>
        </nav>
      </aside>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
};

export default Layout;
