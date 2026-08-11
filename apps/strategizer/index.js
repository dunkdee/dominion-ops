const express = require('express');
const cors = require('cors');
const { GoogleGenAI } = require('@google/genai');

const app = express();
app.use(cors());
app.use(express.json());

const project = 'dominion-ascendant';
const location = 'us-central1';

const client = new GoogleGenAI({
  vertexai: true,
  project,
  location,
});

app.get('/health', (req, res) => {
  res.json({ status: 'ok', ecosystem: 'dominion-ascendant' });
});

app.post('/strategize', async (req, res) => {
  try {
    const { idea } = req.body || {};

    if (!idea) {
      return res.status(400).json({ error: 'idea required' });
    }

    const prompt = `
Return ONLY valid JSON. No markdown. No explanation.
{
  "niche": "",
  "target_customer": "",
  "offer": "",
  "pricing": "",
  "traffic_strategy": [],
  "automation_stack": [],
  "estimated_monthly_revenue": "",
  "execution_plan": []
}
Idea: ${idea}
`;

    const result = await client.models.generateContent({
      model: 'gemini-2.5-flash-lite',
      contents: prompt
    });

    let text = result.text || '';
    text = text.replace(/```json|```/g, '').trim();

    return res.json(JSON.parse(text));
  } catch (err) {
    console.error('Ecosystem Error:', err);
    return res.status(500).json({
      error: 'Vertex AI Error',
      details: err.message
    });
  }
});

const PORT = process.env.PORT || 8080;
app.listen(PORT, () => {
  console.log(`Dominion Strategizer listening on ${PORT}`);
});
