import React from 'react';
import { ProjectProvider, useProject } from './context/ProjectContext';
import { AppLayout } from './layouts/AppLayout';
import { LandingPage } from './pages/LandingPage';
import { UploadPage } from './pages/UploadPage';
import { DepthViewerPage } from './pages/DepthViewerPage';
import { DSMViewerPage } from './pages/DSMViewerPage';
import { ExplorerPage } from './pages/ExplorerPage';
import { AnalysisPage } from './pages/AnalysisPage';
import { ValidationPage } from './pages/ValidationPage';
import { MethodologyPage } from './pages/MethodologyPage';
import { ExportModal } from './components/ExportModal';

const MainView: React.FC = () => {
  const { activeTab } = useProject();

  switch (activeTab) {
    case 'landing':
      return <LandingPage />;
    case 'upload':
      return <UploadPage />;
    case 'depth':
      return <DepthViewerPage />;
    case 'dsm':
      return <DSMViewerPage />;
    case 'explorer':
      return <ExplorerPage />;
    case 'analysis':
      return <AnalysisPage />;
    case 'validation':
      return <ValidationPage />;
    case 'methodology':
      return <MethodologyPage />;
    default:
      return <LandingPage />;
  }
};

export const App: React.FC = () => {
  return (
    <ProjectProvider>
      <AppLayout>
        <MainView />
        <ExportModal />
      </AppLayout>
    </ProjectProvider>
  );
};

export default App;
