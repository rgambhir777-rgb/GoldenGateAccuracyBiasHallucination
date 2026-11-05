import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import "./index.css";
import Compare from "./pages/Compare";
import Fairness from "./pages/Fairness";
import Gates from "./pages/Gates";
import Golden from "./pages/Golden";
import Items from "./pages/Items";
import Overview from "./pages/Overview";
import Releases from "./pages/Releases";
import SettingsPage from "./pages/Settings";
import { Empty } from "./components/ui";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/releases" element={<Releases />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/items" element={<Items />} />
          <Route path="/fairness" element={<Fairness />} />
          <Route path="/golden" element={<Golden />} />
          <Route path="/gates" element={<Gates />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Empty title="Page not found" hint="Use the navigation on the left." />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  </React.StrictMode>,
);
