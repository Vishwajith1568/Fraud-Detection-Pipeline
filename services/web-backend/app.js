const { Kafka } = require('kafkajs');
const { Server } = require('socket.io');
const http = require('http');
const mongoose = require('mongoose');
const express = require('express');
const cors = require('cors');
const jwt = require('jsonwebtoken');
const promClient = require('prom-client');

const app = express();
app.use(cors());
app.use(express.json());

// FIX: Read JWT secret from environment variable with fallback
const JWT_SECRET = process.env.JWT_SECRET || 'my-super-secret-enterprise-key-2026';

const collectDefaultMetrics = promClient.collectDefaultMetrics;
collectDefaultMetrics({ register: promClient.register });

const alertsProcessedCounter = new promClient.Counter({
    name: 'fraud_alerts_processed_total',
    help: 'Total number of fraud alerts processed and saved to MongoDB'
});

// CLOUD ROUTE: Connects to Docker's MongoDB
mongoose.connect('mongodb://mongodb:27017/fraud_detection')
    .then(() => console.log('Connected to MongoDB!'))
    .catch(err => console.error('MongoDB Connection Error:', err));

const alertSchema = new mongoose.Schema({
    transaction_id: { type: String, required: true, unique: true },
    user_id: String,
    amount: Number,
    currency: String,
    merchant: String,
    reasons: [String],
    timestamp: mongoose.Schema.Types.Mixed  // FIX: Accept both Number and String timestamps
});
alertSchema.index({ timestamp: -1 });
const Alert = mongoose.model('Alert', alertSchema);

const authenticateToken = (req, res, next) => {
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1];
    if (!token) return res.status(401).json({ error: 'Access Denied: Token Missing' });

    jwt.verify(token, JWT_SECRET, (err, decodedUser) => {
        if (err) return res.status(403).json({ error: 'Forbidden: Invalid or Expired Token' });
        req.user = decodedUser;
        next();
    });
};

app.get('/metrics', async (req, res) => {
    try {
        res.set('Content-Type', promClient.register.contentType);
        res.end(await promClient.register.metrics());
    } catch (err) {
        res.status(500).end(String(err));
    }
});

app.post('/api/login', (req, res) => {
    const { username, password } = req.body;
    if (username === 'admin' && password === 'admin123') {
        const token = jwt.sign({ role: 'security_admin', username: 'admin' }, JWT_SECRET, { expiresIn: '2h' });
        console.log('Admin Logged In. Token Issued.');
        res.json({ success: true, token: token });
    } else {
        res.status(401).json({ success: false, message: 'Invalid Credentials' });
    }
});

app.get('/api/alerts', authenticateToken, async (req, res) => {
    try {
        const history = await Alert.find().sort({ timestamp: -1 }).limit(50);
        res.json(history);
    } catch (err) {
        console.error("Failed to fetch history:", err);
        res.status(500).json({ error: "Internal Server Error" });
    }
});

const server = http.createServer(app);
const io = new Server(server, {
    // FIX: Allow connections from any origin (frontend could be on different ports)
    cors: { origin: '*', methods: ['GET', 'POST'] }
});

// CLOUD ROUTE: Connects to Docker's Kafka
const kafka = new Kafka({
    clientId: 'web-backend',
    brokers: ['kafka:9092']
});
const consumer = kafka.consumer({ groupId: 'frontend-broadcaster-group' });

const run = async () => {
    await consumer.connect();
    await consumer.subscribe({ topic: 'fraud_alerts', fromBeginning: true });
    console.log('Kafka Consumer running in BATCH MODE...');

    await consumer.run({
        eachBatch: async ({ batch, resolveOffset, heartbeat }) => {
            const batchSize = batch.messages.length;
            console.log(`Received Kafka Batch: Processing ${batchSize} alerts...`);

            const alertsToSave = [];
            for (let message of batch.messages) {
                const alertData = JSON.parse(message.value.toString());
                alertsToSave.push(alertData);
                io.emit('new_fraud_alert', alertData);
                resolveOffset(message.offset);
            }

            try {
                await Alert.insertMany(alertsToSave, { ordered: false });
                console.log(`[SUCCESS] Bulk inserted ${alertsToSave.length} records into MongoDB!`);
                alertsProcessedCounter.inc(alertsToSave.length);
            } catch (err) {
                if (err.code === 11000) {
                    console.log(`Batch contained some duplicates, but new records were saved.`);
                    if (err.writeErrors) {
                        const savedCount = alertsToSave.length - err.writeErrors.length;
                        alertsProcessedCounter.inc(savedCount);
                    }
                } else {
                    console.error('Bulk Insert Error:', err);
                }
            }
            await heartbeat();
        },
    });
};

run().catch(console.error);

server.listen(4000, () => {
    console.log('Secured Web Backend listening on port 4000');
});