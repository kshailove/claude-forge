import { createBrowserRouter, type RouteObject } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { Login } from "./pages/Login";
import { Overview } from "./pages/Overview";
import { Teams } from "./pages/Teams";
import { TeamDetail } from "./pages/TeamDetail";
import { Engineers } from "./pages/Engineers";
import { EngineerDetail } from "./pages/EngineerDetail";
import { Incidents } from "./pages/Incidents";
import { Digests } from "./pages/Digests";
import { DigestViewer } from "./pages/DigestViewer";
import { Admin } from "./pages/Admin";
import { AuthGuard } from "./App";

// Placeholder pages for nav items not yet implemented
function ComingSoon({ name }: { name: string }) {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-2">
      <p className="text-lg font-medium">{name}</p>
      <p className="text-sm text-muted-foreground">Coming in a future milestone.</p>
    </div>
  );
}

const protectedRoutes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <Overview /> },
      { path: "teams", element: <Teams /> },
      { path: "teams/:teamId", element: <TeamDetail /> },
      { path: "engineers", element: <Engineers /> },
      { path: "engineers/:userId", element: <EngineerDetail /> },
      { path: "incidents", element: <Incidents /> },
      { path: "digests", element: <Digests /> },
      { path: "digests/:digestId", element: <DigestViewer /> },
      { path: "admin", element: <Admin /> },
    ],
  },
];

export const router = createBrowserRouter([
  { path: "/login", element: <Login /> },
  {
    path: "/",
    element: <AuthGuard />,
    children: protectedRoutes,
  },
]);
