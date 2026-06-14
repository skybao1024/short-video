import { FC, useEffect, useMemo, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Button, Input, Form, Card, Typography } from 'antd';
import { login } from '@/apis/auth';
import { useUserStore } from '@/store/useUserStore';
import { PATHS } from '@/router/paths';
import { showRequestError } from '@/utils/requestError';
import styles from './index.module.scss';

const { Title, Text } = Typography;

const Login: FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { setTokens, setUser, token } = useUserStore();
  const [loading, setLoading] = useState(false);

  const searchParams = new URLSearchParams(location.search);
  const from = searchParams.get('from');

  const redirectPath = useMemo((): string => {
    if (from && from.startsWith('/') && !from.startsWith('//')) {
      return from;
    }
    return PATHS.dashboard;
  }, [from]);

  useEffect(() => {
    if (token) {
      navigate(redirectPath, { replace: true });
    }
  }, [token, navigate, redirectPath]);

  const handleSubmit = async (values: { email: string; password: string }) => {
    setLoading(true);
    try {
      const response = await login(values);
      const authData = response.data.data;

      setTokens(authData.access_token, authData.refresh_token);
      setUser(
        authData.user
          ? {
              id: authData.user.id,
              email: authData.user.email,
              name: [authData.user.first_name, authData.user.last_name].filter(Boolean).join(' ') || null,
              avatar: authData.user.avatar,
            }
          : { email: values.email }
      );
      navigate(redirectPath, { replace: true });
    } catch (error) {
      showRequestError(error, 'Unable to sign in');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <Card className={styles.card}>
        <div className={styles.header}>
          <Title level={2} className={styles.title}>
            Sign In
          </Title>
          <Text className={styles.subtitle}>Welcome back! Please sign in to continue.</Text>
        </div>

        <Form layout="vertical" onFinish={handleSubmit} className={styles.form}>
          <Form.Item
            name="email"
            label="Email"
            rules={[
              { required: true, message: 'Please enter your email' },
              { type: 'email', message: 'Please enter a valid email' },
            ]}
          >
            <Input size="large" placeholder="Enter your email" />
          </Form.Item>

          <Form.Item name="password" label="Password" rules={[{ required: true, message: 'Please enter your password' }]}>
            <Input.Password size="large" placeholder="Enter your password" />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" size="large" loading={loading} block>
              Sign In
            </Button>
          </Form.Item>
        </Form>

        <div className={styles.footer}>
          <Text>Account access is provisioned by your workspace admin.</Text>
        </div>
      </Card>
    </div>
  );
};

export default Login;
