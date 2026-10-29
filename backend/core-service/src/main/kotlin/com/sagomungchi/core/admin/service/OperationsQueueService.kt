package com.sagomungchi.core.admin.service
import com.sagomungchi.core.admin.client.QueueManagementClient
import org.springframework.stereotype.Service
@Service
class OperationsQueueService(private val client: QueueManagementClient) { fun queues()=client.queues() }
