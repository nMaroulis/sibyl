import {
  ArrowDownUp,
  Bell,
  BookOpen,
  Compass,
  Globe2,
  Settings2,
  Sparkles,
  Waves,
} from 'lucide-react';
import { exchangeCategoryIcons } from './category-icons';

export const destinations = [
  { path: '/sibyl', name: 'Sibyl', icon: Sparkles },
  { path: '/account', name: 'Account', icon: exchangeCategoryIcons.account },
  { path: '/markets', name: 'Markets', icon: exchangeCategoryIcons.market },
  { path: '/trade', name: 'Trade', icon: ArrowDownUp },
  { path: '/strategies', name: 'Strategies', icon: Waves },
  { path: '/forecast', name: 'Forecasting', icon: Compass },
  { path: '/news', name: 'News', icon: Globe2 },
  { path: '/oracle', name: 'Agents', icon: Sparkles },
  { path: '/alerts', name: 'Alerts', icon: Bell },
  { path: '/research', name: 'Research', icon: BookOpen },
  { path: '/settings', name: 'Settings', icon: Settings2 },
  { path: '/roadmap', name: 'Coming soon', icon: Compass },
] as const;

export type DestinationPath = (typeof destinations)[number]['path'];

export const defaultPinnedPaths: readonly DestinationPath[] = [
  '/sibyl',
  '/account',
  '/markets',
  '/trade',
  '/strategies',
  '/forecast',
  '/news',
  '/settings',
];

export function normalizePinnedPaths(value: unknown): readonly DestinationPath[] {
  if (!Array.isArray(value)) return defaultPinnedPaths;
  return destinations
    .filter(({ path }) => path === '/account' || value.includes(path))
    .map(({ path }) => path);
}

export const dockStyles = [
  { id: 'glass', label: 'Glass' },
  { id: 'porcelain', label: 'Porcelain' },
  { id: 'graphite', label: 'Graphite' },
  { id: 'aurora', label: 'Aurora' },
] as const;

export type DockStyle = (typeof dockStyles)[number]['id'];

export function isDockStyle(value: unknown): value is DockStyle {
  return dockStyles.some(({ id }) => id === value);
}
