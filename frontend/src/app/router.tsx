import { Route, Routes } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import CaseCreatePage from '../pages/CaseCreatePage';
import CaseDetailPage from '../pages/CaseDetailPage';
import DashboardPage from '../pages/DashboardPage';
import DocumentDetailPage from '../pages/DocumentDetailPage';
import NotFoundPage from '../pages/NotFoundPage';
import WorkflowPage from '../pages/WorkflowPage';

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="cases/new" element={<CaseCreatePage />} />
        <Route path="cases/:caseId" element={<CaseDetailPage />} />
        <Route path="cases/:caseId/documents/:documentId" element={<DocumentDetailPage />} />
        <Route path="workflow/:caseId" element={<WorkflowPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
