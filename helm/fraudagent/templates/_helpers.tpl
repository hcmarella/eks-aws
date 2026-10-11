{{- define "fraudagent.image" -}}{{ .Values.image.repository }}:{{ .Values.image.tag }}{{- end -}}
{{- define "fraudagent.env" -}}
- {name: MODEL_RUNNER, value: {{ .Values.modelRunner | quote }}}
- {name: BEDROCK_MODEL_ID, value: {{ .Values.bedrockModelId | quote }}}
- {name: AWS_REGION, value: {{ .Values.awsRegion | quote }}}
- {name: NAMESPACE, value: {{ .Release.Namespace | quote }}}
- {name: AGENT_IMAGE, value: {{ include "fraudagent.image" . | quote }}}
- name: DATABASE_URL
  valueFrom: {secretKeyRef: {name: {{ .Values.database.existingSecret }}, key: url}}
{{- end -}}
