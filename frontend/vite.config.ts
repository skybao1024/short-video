import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { chunkSplitPlugin } from 'vite-plugin-chunk-split';
import eslintPlugin from 'vite-plugin-eslint';
import { createSvgIconsPlugin } from 'vite-plugin-svg-icons';

const FRONTEND_DEV_PORT = Number(process.env.FRONTEND_DEV_PORT || 3000);
const VITE_HMR_CLIENT_PORT = Number(
  process.env.VITE_HMR_CLIENT_PORT || FRONTEND_DEV_PORT
);
const USE_POLLING =
  process.env.VITE_USE_POLLING === 'true' ||
  process.env.CHOKIDAR_USEPOLLING === 'true';

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react({
      babel: {
        plugins: ['babel-plugin-react-compiler'],
      },
    }),
    chunkSplitPlugin({
      customSplitting: {
        'react-vendor': [/node_modules\/react/, /node_modules\/react-dom/],
        utils: [/src\/utils/, /src\/components/],
      },
    }),
    eslintPlugin(),
    createSvgIconsPlugin({
      iconDirs: [path.resolve(__dirname, 'src/assets/svg')],
      symbolId: 'icon-[dir]-[name]',
      inject: 'body-last',
      customDomId: '__svg_icons',
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    watch: {
      ignored: ['**/node_modules/**', '**/.git/**'],
      interval: USE_POLLING ? 300 : undefined,
      usePolling: USE_POLLING,
    },
    hmr: {
      clientPort: VITE_HMR_CLIENT_PORT,
    },
    proxy: {
      '^/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8003',
        changeOrigin: true,
      },
    },
    host: '0.0.0.0',
    port: FRONTEND_DEV_PORT,
  },
  build: {
    sourcemap: true,
    minify: 'terser',
  },
  esbuild: {
    pure: ['console'],
  },
});
