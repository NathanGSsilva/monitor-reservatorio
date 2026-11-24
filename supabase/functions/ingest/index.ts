Deno.serve(async (req) => {
    if (req.method !== "POST") {
        return Response.json({ error: "Use POST" }, {
            status: 405,
            headers: { Allow: "POST" },
        });
    }

    const ingestKey = Deno.env.get("INGEST_KEY");
    const supabaseUrl = Deno.env.get("SUPABASE_URL");

    const secretKeys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}");
    const adminKey = secretKeys.default || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

    if (!ingestKey || ingestKey.length < 32 || !supabaseUrl || !adminKey) {
        return Response.json({ error: "Configuração incompleta" }, { status: 500 });
    }

    if (req.headers.get("x-ingest-key") !== ingestKey) {
        return Response.json({ error: "Chave de envio inválida" }, { status: 401 });
    }

    const reading = await req.json().catch(() => null);
    const { device_id, message_id, distance_cm, level_pct } = reading ?? {};

    if (
        typeof device_id !== "string" || !/^[a-z0-9_-]{1,40}$/.test(device_id) ||
        typeof message_id !== "string" || !/^[a-zA-Z0-9_-]{1,120}$/.test(message_id) ||
        typeof distance_cm !== "number" || !Number.isFinite(distance_cm) ||
        distance_cm < 0.1 || distance_cm > 99999.9 ||
        typeof level_pct !== "number" || !Number.isFinite(level_pct) ||
        level_pct < 0 || level_pct > 100
    ) {
        return Response.json({ error: "Leitura inválida" }, { status: 400 });
    }

    const headers = new Headers({
        apikey: adminKey,
        "Content-Type": "application/json",
        Prefer: "resolution=ignore-duplicates,return=representation",
    });

    if (!adminKey.startsWith("sb_secret_")) {
        headers.set("Authorization", `Bearer ${adminKey}`);
    }

    try {
        const url = `${supabaseUrl}/rest/v1/readings?on_conflict=device_id,message_id`;
        const result = await fetch(url, {
            method: "POST",
            headers,
            body: JSON.stringify({ device_id, message_id, distance_cm, level_pct }),
            signal: AbortSignal.timeout(10_000),
        });

        if (!result.ok) {
            console.error("Falha ao gravar leitura", result.status, await result.text());
            return Response.json({ error: "Falha ao gravar leitura" }, { status: 500 });
        }

        const [savedReading] = await result.json();

        return Response.json({
            ok: true,
            inserted: Boolean(savedReading),
            reading: savedReading ?? null,
        }, { status: savedReading ? 201 : 200 });
    } catch (error) {
        console.error("Falha na comunicação com o banco", error);
        return Response.json({ error: "Falha ao acessar o banco" }, { status: 502 });
    }
});