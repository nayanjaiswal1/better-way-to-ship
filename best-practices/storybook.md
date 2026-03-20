# Storybook — Component Documentation

## Setup

```bash
npx storybook@latest init
# Installs Storybook with Vite + React automatically

npm install @storybook/addon-a11y @storybook/addon-interactions --save-dev
```

```ts
// .storybook/main.ts
import type { StorybookConfig } from '@storybook/react-vite';

const config: StorybookConfig = {
  stories: ['../src/**/*.stories.@(ts|tsx)'],
  addons: [
    '@storybook/addon-essentials',   // controls, actions, docs, viewport
    '@storybook/addon-a11y',         // accessibility panel
    '@storybook/addon-interactions', // play() function testing
  ],
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
};

export default config;
```

```ts
// .storybook/preview.ts — global decorators
import type { Preview } from '@storybook/react';
import '../src/styles/tokens.css';   // design tokens (dark mode vars)
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient();

const preview: Preview = {
  decorators: [
    (Story) => (
      <QueryClientProvider client={queryClient}>
        <Story />
      </QueryClientProvider>
    ),
  ],
  parameters: {
    layout: 'centered',
    backgrounds: {
      default: 'light',
      values: [
        { name: 'light', value: 'var(--color-bg-primary)' },
        { name: 'dark',  value: '#111827' },
      ],
    },
  },
};

export default preview;
```

---

## Writing Stories

### Simple Component

```tsx
// components/Badge/Badge.stories.tsx
import type { Meta, StoryObj } from '@storybook/react';
import { Badge } from './Badge';

const meta: Meta<typeof Badge> = {
  component: Badge,
  tags: ['autodocs'],              // auto-generate docs page
  argTypes: {
    variant: {
      control: 'select',
      options: ['success', 'warning', 'danger', 'info'],
    },
  },
};

export default meta;
type Story = StoryObj<typeof Badge>;

export const Success: Story = {
  args: { children: 'Active', variant: 'success' },
};

export const Warning: Story = {
  args: { children: 'Pending', variant: 'warning' },
};

export const Danger: Story = {
  args: { children: 'Overdue', variant: 'danger' },
};

// All variants at once
export const AllVariants: Story = {
  render: () => (
    <div style={{ display: 'flex', gap: 8 }}>
      <Badge variant="success">Active</Badge>
      <Badge variant="warning">Pending</Badge>
      <Badge variant="danger">Overdue</Badge>
      <Badge variant="info">Draft</Badge>
    </div>
  ),
};
```

### Component with Async Data (MSW)

```tsx
// components/UserCard/UserCard.stories.tsx
import { http, HttpResponse } from 'msw';
import type { Meta, StoryObj } from '@storybook/react';
import { UserCard } from './UserCard';

const meta: Meta<typeof UserCard> = {
  component: UserCard,
  parameters: {
    msw: {                          // intercept fetch in Storybook
      handlers: [
        http.get('/api/v1/users/me', () =>
          HttpResponse.json({
            id: '01ARZ3NDEKTSV4RRFFQ69G5FAV',
            name: 'Alice Smith',
            email: 'alice@example.com',
            role: 'admin',
          })
        ),
      ],
    },
  },
};

export default meta;
type Story = StoryObj<typeof UserCard>;

export const Default: Story = {};

export const Loading: Story = {
  parameters: {
    msw: {
      handlers: [
        http.get('/api/v1/users/me', async () => {
          await new Promise(r => setTimeout(r, 99999));  // hang forever
        }),
      ],
    },
  },
};

export const Error: Story = {
  parameters: {
    msw: {
      handlers: [
        http.get('/api/v1/users/me', () =>
          HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 })
        ),
      ],
    },
  },
};
```

### Form with Interactions (play function)

```tsx
// components/LoginForm/LoginForm.stories.tsx
import { within, userEvent, expect } from '@storybook/test';
import type { Meta, StoryObj } from '@storybook/react';
import { LoginForm } from './LoginForm';

const meta: Meta<typeof LoginForm> = {
  component: LoginForm,
};

export default meta;
type Story = StoryObj<typeof LoginForm>;

export const Default: Story = {};

// Simulate user filling in the form
export const FilledIn: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    await userEvent.type(
      canvas.getByLabelText('Email'),
      'alice@example.com',
    );

    await userEvent.type(
      canvas.getByLabelText('Password'),
      'secret123',
    );

    // Assert button becomes enabled
    await expect(canvas.getByRole('button', { name: 'Sign in' }))
      .not.toBeDisabled();
  },
};

// Simulate validation errors
export const ValidationErrors: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    await userEvent.click(canvas.getByRole('button', { name: 'Sign in' }));

    await expect(canvas.getByText('Email is required')).toBeInTheDocument();
    await expect(canvas.getByText('Password is required')).toBeInTheDocument();
  },
};
```

---

## Design System — Shared Token Stories

```tsx
// stories/DesignTokens.stories.tsx — visual reference for the team
import type { Meta, StoryObj } from '@storybook/react';

function ColorSwatch({ name, var: cssVar }: { name: string; var: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
      <div style={{
        width: 48, height: 48, borderRadius: 8,
        background: `var(${cssVar})`,
        border: '1px solid var(--color-border)',
      }} />
      <div>
        <div style={{ fontWeight: 600 }}>{name}</div>
        <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{cssVar}</div>
      </div>
    </div>
  );
}

const meta: Meta = { title: 'Design System/Colors' };
export default meta;

export const Colors: StoryObj = {
  render: () => (
    <div>
      <ColorSwatch name="Background Primary"   var="--color-bg-primary" />
      <ColorSwatch name="Background Secondary" var="--color-bg-secondary" />
      <ColorSwatch name="Text Primary"         var="--color-text-primary" />
      <ColorSwatch name="Text Muted"           var="--color-text-muted" />
      <ColorSwatch name="Accent"               var="--color-accent" />
      <ColorSwatch name="Danger"               var="--color-danger" />
      <ColorSwatch name="Success"              var="--color-success" />
    </div>
  ),
};
```

---

## Visual Regression Testing — Chromatic

Catch unintended UI changes in CI.

```bash
npm install --save-dev chromatic
```

```yaml
# .github/workflows/chromatic.yml
name: Chromatic

on: [push]

jobs:
  chromatic:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history for baseline comparison

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - run: npm ci

      - name: Publish to Chromatic
        uses: chromaui/action@latest
        with:
          projectToken: ${{ secrets.CHROMATIC_PROJECT_TOKEN }}
          exitZeroOnChanges: true    # don't fail — just flag for review
          onlyChanged: true          # only test stories affected by changes
```

---

## Accessibility Testing in Stories

```tsx
// Any story automatically gets a11y panel with Addon A11y
// Tag stories that have known issues so they're tracked

export const LowContrastLegacy: Story = {
  args: { variant: 'ghost' },
  parameters: {
    a11y: {
      // Document known issues while fixing them
      config: {
        rules: [{ id: 'color-contrast', enabled: false }],
      },
    },
  },
};
```

```bash
# Run a11y checks headlessly in CI
npx storybook build
npx axe-storybook --storybook-url ./storybook-static
```

---

## Storybook Checklist

- [ ] Every shared component has a story
- [ ] Loading, error, empty states all have stories
- [ ] Forms have `play()` interaction tests
- [ ] Design tokens documented in `DesignSystem/Colors` story
- [ ] Dark mode variant tested via backgrounds addon
- [ ] Chromatic in CI — visual diffs on every PR
- [ ] A11y addon enabled — zero violations in stories
- [ ] MSW handlers in stories for components that fetch data
- [ ] Stories colocated with components (`Button/Button.stories.tsx`)
