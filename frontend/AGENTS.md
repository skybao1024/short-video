# AGENTS.md

Development conventions and guidelines for AI coding assistants.

## Code Style

### Naming Conventions

- **Components**: PascalCase (e.g., `UserProfile.tsx`, `LoginForm.tsx`)
- **Utilities/Hooks**: camelCase (e.g., `useUserStore.ts`, `formatDate.ts`)
- **Styles**: `index.module.scss` in component directories
- **Constants**: UPPER_SNAKE_CASE (e.g., `API_BASE_URL`)

### File Organization

```
src/
├── components/
│   └── ComponentName/
│       ├── index.tsx
│       └── index.module.scss
├── pages/
│   └── PageName/
│       ├── index.tsx
│       └── index.module.scss
```

## React Patterns

### Component Template

```tsx
import { FC } from 'react';
import styles from './index.module.scss';

interface ComponentProps {
  // Define props
}

const Component: FC<ComponentProps> = ({ ...props }) => {
  return <div className={styles.container} />;
};

export default Component;
```

### Store Template (Zustand)

```tsx
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface StoreState {
  // State types
}

export const useStore = create<StoreState>()(
  persist(
    (set) => ({
      // Initial state and actions
    }),
    {
      name: 'storeName',
      storage: createJSONStorage(() => localStorage),
    }
  )
);
```

## Styling Guidelines

### Use SCSS Modules

```scss
.container {
  display: flex;
  background-color: var(--bg-primary);
  color: var(--text-primary);
}
```

### CSS Variables

Always use CSS variables for colors:
- `--bg-primary`: Primary background
- `--text-primary`: Primary text color
- `--text-secondary`: Secondary text color
- `--border-default`: Default border color

**Never hardcode colors** like `#ffffff` or `rgba(0,0,0,0.5)`.

## Ant Design Guidelines

### Button Usage

Use Ant Design's built-in size prop:

```tsx
// Correct
<Button size="large">Submit</Button>
<Button size="middle">Submit</Button>
<Button size="small">Submit</Button>

// Incorrect - Don't override button size with CSS
```

### Message API

Use the global message API from context:

```tsx
import { App } from 'antd';

const Component = () => {
  const { message } = App.useApp();

  const handleClick = () => {
    message.success('Operation successful');
  };
};
```

## HTTP Requests

### Using the HTTP Client

```tsx
import service from '@/utils/https';

// The interceptor automatically:
// - Adds Authorization header
// - Handles 401 errors
// - Shows error messages

const fetchData = async () => {
  const response = await service.get('/api/data');
  return response.data;
};
```

### Suppress Error Messages

```tsx
// Use hideMessageModal to suppress automatic error display
await service.get('/api/data', { hideMessageModal: true });
```

## Path Aliases

Always use `@/` for imports:

```tsx
// Correct
import { useUserStore } from '@/store/useUserStore';
import styles from './index.module.scss';

// Incorrect
import { useUserStore } from '../../../store/useUserStore';
```
