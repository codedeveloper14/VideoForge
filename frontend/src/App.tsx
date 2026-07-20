import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import { TabsProvider } from "./context/TabsContext";
import { GenerationStatusProvider } from "./context/GenerationStatusContext";
import ProtectedRoute from "./components/ProtectedRoute";
import AppLayout from "./layouts/AppLayout";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import HomePage from "./pages/HomePage";
import Idea2VideoPage from "./pages/Idea2VideoPage";
import GuionPage from "./pages/GuionPage";
import VozPage from "./pages/VozPage";
import ImagenPage from "./pages/ImagenPage";
import VideoPage from "./pages/VideoPage";
import RenderPage from "./pages/RenderPage";
import EditorPage from "./pages/EditorPage";
import ProjectsPage from "./pages/ProjectsPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import PlansPage from "./pages/PlansPage";
import ProfilePage from "./pages/ProfilePage";
import HelpPage from "./pages/HelpPage";
import DocumentacionPage from "./pages/DocumentacionPage";
import TareasPage from "./pages/TareasPage";
import AdminDocsPage from "./pages/AdminDocsPage";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ThemeProvider>
          <TabsProvider>
            <GenerationStatusProvider>
            <Routes>
              <Route path="/" element={<Navigate to="/app/home" replace />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />

              <Route element={<ProtectedRoute />}>
                <Route path="/app" element={<AppLayout />}>
                  <Route index element={<Navigate to="home" replace />} />
                  <Route path="home" element={<HomePage />} />
                  <Route path="idea2video" element={<Idea2VideoPage />} />
                  <Route path="tareas" element={<TareasPage />} />
                  <Route path="documentacion" element={<DocumentacionPage />} />
                  <Route path="guion" element={<GuionPage />} />
                  <Route path="voz" element={<VozPage />} />
                  <Route path="imagen" element={<ImagenPage />} />
                  <Route path="video" element={<VideoPage />} />
                  <Route path="render" element={<RenderPage />} />
                  <Route path="editor" element={<EditorPage />} />
                  <Route path="editor/:proyecto" element={<EditorPage />} />
                  <Route path="proyectos" element={<ProjectsPage />} />
                  <Route path="proyectos/:nombre" element={<ProjectDetailPage />} />
                  <Route path="planes" element={<PlansPage />} />
                  <Route path="ajustes" element={<ProfilePage />} />
                  <Route path="perfil" element={<Navigate to="/app/ajustes" replace />} />
                  <Route path="ayuda" element={<HelpPage />} />
                  <Route path="admin/docs" element={<AdminDocsPage />} />
                </Route>
              </Route>

              <Route path="*" element={<Navigate to="/app/home" replace />} />
            </Routes>
            </GenerationStatusProvider>
          </TabsProvider>
        </ThemeProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
