import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { LayoutDashboard, Users, User, AlertCircle, FileText, LogOut, Settings } from "lucide-react";
import { useAuthStore } from "@/stores/authStore";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true, adminOnly: false },
  { to: "/teams", label: "Teams", icon: Users, end: false, adminOnly: false },
  { to: "/engineers", label: "Engineers", icon: User, end: false, adminOnly: false },
  { to: "/incidents", label: "Incidents", icon: AlertCircle, end: false, adminOnly: false },
  { to: "/digests", label: "Digests", icon: FileText, end: false, adminOnly: false },
  { to: "/admin", label: "Admin", icon: Settings, end: false, adminOnly: true },
] as const;

export function AppLayout() {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Top navigation */}
      <header className="sticky top-0 z-50 border-b border-border bg-card shadow-sm">
        <div className="mx-auto flex h-14 max-w-screen-xl items-center gap-6 px-6">
          {/* Logo / brand */}
          <span className="shrink-0 text-sm font-bold tracking-tight">
            Engg Intelligence
          </span>

          {/* Nav tabs */}
          <nav className="flex flex-1 items-center gap-1">
            {NAV_ITEMS.filter(({ adminOnly }) => !adminOnly || user?.role === "admin").map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {label}
              </NavLink>
            ))}
          </nav>

          {/* User avatar + logout */}
          <div className="flex shrink-0 items-center gap-3">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold uppercase text-primary">
                {user?.username?.[0] ?? "?"}
              </div>
              <div className="hidden sm:block">
                <p className="text-xs font-medium leading-tight">
                  {user?.username ?? "User"}
                </p>
                <p className="text-xs capitalize text-muted-foreground">
                  {user?.role ?? ""}
                </p>
              </div>
            </div>
            <button
              onClick={handleLogout}
              title="Sign out"
              className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Page content */}
      <main className="mx-auto w-full max-w-screen-xl flex-1 px-6 py-6">
        <Outlet />
      </main>
    </div>
  );
}
