import { apiPostCommand, createIdempotencyKey, OpenVigilApiError } from "./api-client.ts";

interface UploadGrant {
  readonly artifact_uri: string;
  readonly upload_url: string;
  readonly required_headers: Readonly<Record<string, string>>;
  readonly expires_at: string;
}

export interface ArtifactCommandInput {
  readonly file: File;
  readonly presignPath: string;
  readonly presignBody?: Readonly<Record<string, unknown>>;
  readonly commandPath: string;
  readonly commandBody: Readonly<Record<string, unknown>>;
}

function isGrant(value: unknown): value is UploadGrant {
  if (!value || typeof value !== "object") return false;
  const row = value as Partial<UploadGrant>;
  if (
    typeof row.artifact_uri !== "string" ||
    !row.artifact_uri.startsWith("minio://") ||
    typeof row.upload_url !== "string" ||
    !/^https?:\/\//.test(row.upload_url) ||
    !row.required_headers ||
    typeof row.required_headers !== "object" ||
    Object.values(row.required_headers).some((header) => typeof header !== "string") ||
    typeof row.expires_at !== "string" ||
    !Number.isFinite(Date.parse(row.expires_at))
  )
    return false;
  return true;
}

interface PendingUpload {
  readonly input: ArtifactCommandInput;
  readonly signature: string;
  readonly digest: string;
  presignKey: string;
  readonly commandKey: string;
  grant: UploadGrant | null;
  uploaded: boolean;
}

/** Retry the same upload and frozen business command after an unknown result. */
export class StructuralArtifactCommand {
  private pending: PendingUpload | null = null;
  private running = false;
  resultUnknown = false;

  async run<T>(
    input: ArtifactCommandInput,
    validateResult: (value: unknown) => value is T,
  ): Promise<T> {
    if (this.running) throw new Error("已有制品命令正在提交。");
    this.running = true;
    let commandStage = false;
    try {
      if (!this.resultUnknown) {
        if (!input.file.size || input.file.size > 50 * 1024 * 1024)
          throw new Error("证据文件必须在 1 Byte 到 50 MiB 之间。");
        const digestBytes = await crypto.subtle.digest("SHA-256", await input.file.arrayBuffer());
        const digest = [...new Uint8Array(digestBytes)]
          .map((byte) => byte.toString(16).padStart(2, "0"))
          .join("");
        const signature = JSON.stringify({
          ...input,
          file: { name: input.file.name, sha256: digest },
        });
        if (!this.pending || this.pending.signature !== signature) {
          this.pending = {
            input: {
              ...input,
              presignBody: structuredClone(input.presignBody),
              commandBody: structuredClone(input.commandBody),
            },
            signature,
            digest,
            presignKey: createIdempotencyKey("structural-upload"),
            commandKey: createIdempotencyKey("structural-artifact"),
            grant: null,
            uploaded: false,
          };
        }
      }
      const pending = this.pending;
      if (!pending) throw new Error("没有可核验的制品命令。");
      // Once PUT succeeded the command can be replayed without uploading again,
      // including after the short upload URL expires.
      if (
        !pending.uploaded &&
        pending.grant &&
        Date.parse(pending.grant.expires_at) <= Date.now()
      ) {
        pending.grant = null;
        pending.presignKey = createIdempotencyKey("structural-upload");
      }
      if (!pending.grant) {
        commandStage = true;
        const grant = await apiPostCommand<unknown>(
          pending.input.presignPath,
          {
            ...pending.input.presignBody,
            file_name: pending.input.file.name,
            artifact_sha256: pending.digest,
          },
          pending.presignKey,
        );
        if (!isGrant(grant))
          throw new OpenVigilApiError(
            0,
            "COMMAND_RESULT_UNKNOWN",
            "上传授权响应不完整，请重试同一命令核验。",
            null,
            pending.presignKey,
          );
        pending.grant = grant;
      }
      if (!pending.uploaded) {
        commandStage = false;
        if (Date.parse(pending.grant.expires_at) <= Date.now())
          throw new Error("上传授权已过期，请重试以获取新的短时授权。");
        const uploaded = await fetch(pending.grant.upload_url, {
          method: "PUT",
          credentials: "omit",
          headers: pending.grant.required_headers,
          body: pending.input.file,
        });
        if (!uploaded.ok) throw new Error(`对象存储上传失败（HTTP ${uploaded.status}）。`);
        await uploaded.arrayBuffer();
        pending.uploaded = true;
      }
      commandStage = true;
      const result = await apiPostCommand<unknown>(
        pending.input.commandPath,
        {
          ...pending.input.commandBody,
          artifact_uri: pending.grant.artifact_uri,
          artifact_sha256: pending.digest,
        },
        pending.commandKey,
      );
      if (!validateResult(result))
        throw new OpenVigilApiError(
          0,
          "COMMAND_RESULT_UNKNOWN",
          "制品命令响应不完整，请重试同一命令核验。",
          null,
          pending.commandKey,
        );
      this.pending = null;
      this.resultUnknown = false;
      return result;
    } catch (cause) {
      this.resultUnknown = commandStage && cause instanceof OpenVigilApiError && cause.status === 0;
      throw cause;
    } finally {
      this.running = false;
    }
  }
}
