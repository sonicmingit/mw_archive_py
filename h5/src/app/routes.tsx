import { createBrowserRouter } from 'react-router';
import { Layout } from './components/Layout';
import { Overview } from './pages/Overview';
import { Library } from './pages/Library';
import { Archive } from './pages/Archive';
import { Settings } from './pages/Settings';
import { ModelDetail } from './pages/ModelDetail';
import { ScanImport } from './pages/ScanImport';
import { OrganizeDir } from './pages/OrganizeDir';

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, Component: Overview },
      { path: "library", Component: Library },
      { path: "archive", Component: Archive },
      { path: "settings", Component: Settings },
      { path: "model/:id", Component: ModelDetail },
      { path: "scan", Component: ScanImport },
      { path: "organize", Component: OrganizeDir },
    ],
  },
]);
