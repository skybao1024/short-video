# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**frontend**: A React application built with Vite + React 19 + TypeScript.

Core Tech Stack: React 19, React Router 7, Zustand, Axios, Ant Design 6, SCSS Modules.

## Common Commands

```bash
pnpm install      # Install dependencies
pnpm dev          # Start dev server (localhost:3000)
pnpm build        # Production build
pnpm type-check   # Type check
pnpm lint         # Code lint
```

## Directory Structure

```
src/
├── pages/          # Route-level pages
├── components/     # Reusable components (including Layout/)
├── apis/           # API request modules
├── router/         # Route configuration and guards
├── store/          # Zustand stores
├── hooks/          # Custom hooks
├── context/        # React Context
├── utils/          # Utility functions (axios instance, etc.)
├── types/          # Type definitions
├── theme/          # Ant Design theme configuration
└── assets/
    ├── svg/        # SVG icons (with vite-plugin-svg-icons)
    └── styles/     # Global styles and theme variables
```

## Core Modules

| Module | Entry File | Description |
|--------|-----------|-------------|
| Route Config | `src/router/routes.tsx` | Lazy loading + Suspense, path constants in `paths.ts` |
| User State | `src/store/useUserStore.ts` | Persisted user/token storage |
| HTTP Client | `src/utils/https.ts` | Auto-inject Token, 401 handling |
| Message API | `src/utils/messageClient.ts` | Global message API |
| Theme Config | `src/theme/antdTheme.ts` | Ant Design Token configuration |

## Key Conventions

| Convention | Description |
|------------|-------------|
| Naming | Components `PascalCase.tsx`, Utils `camelCase.ts`, Styles `index.module.scss` |
| Path Alias | `@` points to `src/`, avoid `../../../../` relative paths |
| Styling | Prefer SCSS Modules, use CSS variables for theme colors |
| Button Standards | Use Ant Design `size` prop, avoid CSS size overrides |

## Environment Configuration

- Development: `.env.dev`
- Production: `.env.prod`
- API Proxy: See `vite.config.ts` server.proxy
