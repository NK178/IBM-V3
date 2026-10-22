// Render Web Service: serves the chat + Outputs sidebar page and signs
// watsonx Orchestrate embed JWTs so the private key never reaches the browser.
const express = require("express");
const cookieParser = require("cookie-parser");
const jwt = require("jsonwebtoken");
const NodeRSA = require("node-rsa");
const crypto = require("crypto");
const path = require("path");

// PEM keys can be pasted into Render as multi-line values, or as one line with literal \n.
const pem = (v) => (v || "").replace(/\\n/g, "\n").trim();

const PRIVATE_KEY = pem(process.env.WXO_PRIVATE_KEY);   // your RS256 private key
const IBM_PUBLIC_KEY = pem(process.env.IBM_PUBLIC_KEY); // ibmPublic.key.pub from wxO
const TOKEN_TTL = process.env.TOKEN_TTL || "1h";

const missing = ["WXO_PRIVATE_KEY", "IBM_PUBLIC_KEY", "WXO_ORCHESTRATION_ID", "WXO_HOST_URL", "WXO_AGENT_ID", "WXO_AGENT_ENV_ID"]
  .filter((k) => !process.env[k]);
if (missing.length) console.warn("Missing env vars:", missing.join(", "));

const app = express();
app.set("trust proxy", 1); // Render terminates HTTPS in front of the app
app.use(cookieParser());
app.use(express.static(path.join(__dirname, "public")));

// Non-secret embed settings for the browser.
app.get("/config", (_req, res) => {
  res.json({
    orchestrationID: process.env.WXO_ORCHESTRATION_ID,
    hostURL: process.env.WXO_HOST_URL,
    deploymentPlatform: process.env.WXO_DEPLOYMENT_PLATFORM || "ibmcloud",
    crn: process.env.WXO_CRN,
    agentId: process.env.WXO_AGENT_ID,
    agentEnvironmentId: process.env.WXO_AGENT_ENV_ID,
  });
});

// Signed JWT for wxOConfiguration.token (also used on authTokenNeeded refresh).
app.get("/createJWT", (req, res) => {
  try {
    let userId = req.cookies["ANONYMOUS-USER-ID"];
    if (!userId) {
      userId = `anon-${crypto.randomUUID()}`;
      res.cookie("ANONYMOUS-USER-ID", userId, {
        httpOnly: true, secure: true, sameSite: "lax", maxAge: 45 * 24 * 60 * 60 * 1000,
      });
    }

    // user_payload is encrypted with IBM's public key; only wxO can read it.
    const userPayload = { name: "Boss", custom_user_id: userId };
    const encrypted = new NodeRSA(IBM_PUBLIC_KEY).encrypt(JSON.stringify(userPayload), "base64");

    const token = jwt.sign(
      {
        sub: userId,
        user_payload: encrypted,
        context: { name: "Boss", role: "executive" }, // readable by the client, keep non-sensitive
      },
      PRIVATE_KEY,
      { algorithm: "RS256", expiresIn: TOKEN_TTL }
    );
    res.type("text/plain").send(token);
  } catch (err) {
    console.error("JWT creation failed:", err.message);
    res.status(500).type("text/plain").send("Could not create token");
  }
});

app.get("/healthz", (_req, res) => res.send("ok"));

const PORT = process.env.PORT || 5555;
app.listen(PORT, "0.0.0.0", () => console.log(`Listening on ${PORT}`));
