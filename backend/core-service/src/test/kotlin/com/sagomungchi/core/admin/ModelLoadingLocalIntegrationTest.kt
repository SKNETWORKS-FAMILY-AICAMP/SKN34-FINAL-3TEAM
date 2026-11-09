package com.sagomungchi.core.admin

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core.admin.service.*
import com.sagomungchi.core.account.service.TokenService
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.core.env.Environment
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import java.nio.file.Files
import java.nio.file.Path
import java.util.UUID
import java.util.concurrent.TimeUnit
import kotlin.test.*

@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named="MODEL_LOADING_LOCAL",matches="true")
class ModelLoadingLocalIntegrationTest : IntegrationTestSupport() {
    @Autowired lateinit var env: Environment
    @Autowired lateinit var versions: ModelVersionService
    @Autowired lateinit var reports: ModelLoadingService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var mvc: MockMvc
    @Test fun `two scoring processes publish through RabbitMQ into core database and admin HTTP`() {
        val name="m2-local-"+UUID.randomUUID().toString().take(8)
        val actor=account(jdbc,"ADMIN","SERVICE_OPS")
        val old=versions.register(registration(name,"old"),actor)
        versions.activate(old.id,approval(),actor)
        val current=versions.register(registration(name,"current"),actor)
        versions.activate(current.id,approval(),actor)
        val root=Path.of("../scoring-service").toAbsolutePath().normalize()
        val python=System.getenv("SCORING_TEST_PYTHON") ?: root.resolve(".venv/Scripts/python.exe").toString()
        val processes=listOf(false,true).map { fail ->
            val builder=ProcessBuilder(python,"-m","tests.loading_replica").directory(root.toFile()).redirectErrorStream(true)
            builder.environment().putAll(mapOf("TEST_MODEL_NAME" to name,"POD_NAME" to if(fail) "local-scoring-fail" else "local-scoring-ok",
                "TEST_FAIL" to fail.toString(), "TEST_AMQP_URL" to "amqp://"+env.getProperty("spring.rabbitmq.username")+":"+env.getProperty("spring.rabbitmq.password")+"@"+env.getProperty("spring.rabbitmq.host")+":"+env.getProperty("spring.rabbitmq.port")+"/"))
            builder.start()
        }
        try {
            processes.forEach { assertTrue(it.waitFor(40,TimeUnit.SECONDS)); assertEquals(0,it.exitValue(),it.inputStream.bufferedReader().readText()) }
            val deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(20)
            while(System.nanoTime()<deadline && jdbc.queryForObject("SELECT count(*) FROM model_loading_report",Int::class.java)!! < 2) Thread.sleep(100)
            val access=tokens.access(session(jdbc,actor,"ADMIN"))
            val response=mvc.get("/api/v1/admin/model-loading") { header("Authorization","Bearer $access") }.andExpect { status { isOk() } }.andReturn().response.contentAsString
            val body=json.readTree(response)
            val summary=body["summaries"].first { it["name"].asText()==name }
            assertEquals(2,summary["observedPods"].asInt()); assertEquals(1,summary["loadedPods"].asInt())
            assertEquals("local-scoring-fail",summary["failedPods"][0].asText())
            val dir=Path.of("../../output/issue370-local");Files.createDirectories(dir)
            Files.writeString(dir.resolve("loading.json"),response)
            Files.writeString(dir.resolve("version.json"),json.writeValueAsString(versions.list(null,0,100).items.first { it.id==current.id }))
        } finally { processes.filter { it.isAlive }.forEach { it.destroyForcibly() } }
    }
}
