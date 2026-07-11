import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
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
import TareasPage from "./pages/TareasPage";
import ProjectsPage from "./pages/ProjectsPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import PlansPage from "./pages/PlansPage";
import ProfilePage from "./pages/ProfilePage";
import HelpPage from "./pages/HelpPage";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Navigate to="/app/home" replace />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          <Route element={<ProtectedRoute />}>
            <Route path="/app" element={<AppLayout />}>
              <Route index element={<Navigate to="home" replace />} />
              <Route path="home" element={<HomePage />} />
              <Route path="idea2video" element={<Idea2VideoPage />} />
              <Route path="guion" element={<GuionPage />} />
              <Route path="voz" element={<VozPage />} />
              <Route path="imagen" element={<ImagenPage />} />
              <Route path="video" element={<VideoPage />} />
              <Route path="render" element={<RenderPage />} />
              <Route path="editor" element={<EditorPage />} />
              <Route path="editor/:proyecto" element={<EditorPage />} />
              <Route path="tareas" element={<TareasPage />} />
              <Route path="proyectos" element={<ProjectsPage />} />
              <Route path="proyectos/:nombre" element={<ProjectDetailPage />} />
              <Route path="planes" element={<PlansPage />} />
              <Route path="perfil" element={<ProfilePage />} />
              <Route path="ayuda" element={<HelpPage />} />
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/app/home" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
