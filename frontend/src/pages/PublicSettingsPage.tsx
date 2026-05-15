import { useState } from "react";
import { Key, ExternalLink, Settings } from "lucide-react";
import { settingsApi } from "@/services/api";
import toast from "react-hot-toast";
import { useNavigate } from "react-router-dom";

export function PublicSettingsPage() {
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const navigate = useNavigate();

  const handleSave = async () => {
    try {
      await settingsApi.set("youtube_client_id", clientId, true);
      await settingsApi.set("youtube_client_secret", clientSecret, true);
      toast.success("Google API credentials saved! You can now sign in.");
      setClientId("");
      setClientSecret("");
      navigate("/login");
    } catch (e: any) {
      toast.error("Failed to save credentials");
    }
  };

  return (
    <div className="h-full bg-background-light dark:bg-background-dark flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <Settings className="w-10 h-10 text-primary mx-auto mb-2" />
          <h1 className="text-2xl font-bold">API Setup</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Configure Google OAuth to enable YouTube login
          </p>
        </div>

        <div className="card p-6 space-y-4">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
              <Key className="w-5 h-5 text-primary" />
            </div>
            <h2 className="text-lg font-semibold">Google Cloud Credentials</h2>
          </div>

          <ol className="text-sm text-gray-600 dark:text-gray-400 space-y-2 list-decimal pl-4">
            <li>
              Go to the{" "}
              <a
                href="https://console.cloud.google.com/apis/credentials"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline inline-flex items-center gap-1"
              >
                Google Cloud Console
                <ExternalLink className="w-3 h-3" />
              </a>
            </li>
            <li>
              Create a project and enable the{" "}
              <strong>YouTube Data API v3</strong>
            </li>
            <li>
              Create an <strong>OAuth 2.0 Client ID</strong> (Web application
              type)
            </li>
            <li>
              Add{" "}
              <code className="bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded text-xs">
                http://localhost:8080/callback
              </code>{" "}
              as a redirect URI
            </li>
            <li>Copy the Client ID and Client Secret below</li>
          </ol>

          <div className="space-y-3">
            <input
              type="password"
              placeholder="OAuth Client ID"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              className="input"
            />
            <input
              type="password"
              placeholder="OAuth Client Secret"
              value={clientSecret}
              onChange={(e) => setClientSecret(e.target.value)}
              className="input"
            />
            <button
              onClick={handleSave}
              className="cursor-pointer btn-primary w-full"
            >
              Save & Go to Login
            </button>
          </div>
        </div>

        <div className="text-center mt-6">
          <button
            onClick={() => navigate("/login")}
            className="cursor-pointer text-sm text-primary hover:underline"
          >
            ← Back to login
          </button>
        </div>
      </div>
    </div>
  );
}
