import { ApolloProvider } from "@apollo/client";
import { BrowserRouter, HashRouter, Route, Routes } from "react-router-dom";
import { apollo, DEMO_MODE } from "@/api/client";
import { AuthProvider } from "@/auth/AuthContext";
import { SiteProvider } from "@/components/SiteContext";
import { Layout } from "@/components/Layout";
import { Overview } from "@/pages/Overview";
import { Sensors } from "@/pages/Sensors";
import { SensorDetail } from "@/pages/SensorDetail";
import { Alerts } from "@/pages/Alerts";
import { Commands } from "@/pages/Commands";
import { Thresholds } from "@/pages/Thresholds";
import { Notifications } from "@/pages/Notifications";

// GitHub Pages does not rewrite unknown paths to index.html — when the demo
// is hosted there we use HashRouter so /#/alerts works without server-side
// config. In normal dev we keep the clean BrowserRouter URLs.
const Router = DEMO_MODE ? HashRouter : BrowserRouter;

export default function App() {
  return (
    <ApolloProvider client={apollo}>
      <AuthProvider>
        <SiteProvider>
          <Router>
            <Routes>
              <Route element={<Layout />}>
                <Route index element={<Overview />} />
                <Route path="sensors" element={<Sensors />} />
                <Route path="sensors/:sensorId" element={<SensorDetail />} />
                <Route path="alerts" element={<Alerts />} />
                <Route path="thresholds" element={<Thresholds />} />
                <Route path="commands" element={<Commands />} />
                <Route path="notifications" element={<Notifications />} />
                <Route
                  path="*"
                  element={
                    <div className="text-slate-500">
                      Página não encontrada.
                    </div>
                  }
                />
              </Route>
            </Routes>
          </Router>
        </SiteProvider>
      </AuthProvider>
    </ApolloProvider>
  );
}
