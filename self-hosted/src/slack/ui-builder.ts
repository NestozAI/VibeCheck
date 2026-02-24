/**
 * Slack Block Kit UI builders
 */

import { WORK_DIR } from "../config.js";

type Block = Record<string, unknown>;

export function buildApprovalBlocks(
  taskId: string,
  untrustedPaths: string[],
  userMessage: string,
): Block[] {
  const pathList = untrustedPaths.map((p) => `• \`${p}\``).join("\n");

  return [
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: `*Security Warning*\n\nAI is trying to access the following paths:\n${pathList}`,
      },
    },
    {
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: `Request: _${userMessage.slice(0, 100)}${userMessage.length > 100 ? "..." : ""}_`,
        },
      ],
    },
    {
      type: "actions",
      elements: [
        {
          type: "button",
          text: { type: "plain_text", text: "Approve & Run", emoji: true },
          style: "primary",
          action_id: "approve_access",
          value: taskId,
        },
        {
          type: "button",
          text: { type: "plain_text", text: "Approve (Permanent)", emoji: true },
          action_id: "approve_permanent",
          value: taskId,
        },
        {
          type: "button",
          text: { type: "plain_text", text: "Deny", emoji: true },
          style: "danger",
          action_id: "deny_access",
          value: taskId,
        },
      ],
    },
  ];
}

export function buildMessageWithDeleteButton(
  text: string,
  messageId?: string,
): Block[] {
  const id = messageId ?? Math.random().toString(36).slice(2, 10);

  return [
    {
      type: "section",
      text: { type: "mrkdwn", text },
    },
    {
      type: "actions",
      elements: [
        {
          type: "button",
          text: { type: "plain_text", text: "Delete", emoji: true },
          action_id: "delete_message",
          value: id,
        },
      ],
    },
  ];
}

export function buildTrustedPathsBlocks(
  trustedPaths: string[],
): Block[] {
  const blocks: Block[] = [
    {
      type: "header",
      text: { type: "plain_text", text: "Trusted Paths List", emoji: true },
    },
    { type: "divider" },
  ];

  if (trustedPaths.length === 0) {
    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: "_No registered paths._" },
    });
  } else {
    for (const p of trustedPaths) {
      const isDefault = p === WORK_DIR;
      const block: Block = {
        type: "section",
        text: {
          type: "mrkdwn",
          text: `\`${p}\`` + (isDefault ? " _(default)_" : ""),
        },
      };

      if (!isDefault) {
        block.accessory = {
          type: "button",
          text: { type: "plain_text", text: "Remove", emoji: true },
          style: "danger",
          action_id: "remove_trusted_path",
          value: p,
        };
      }

      blocks.push(block);
    }
  }

  blocks.push({ type: "divider" });
  blocks.push({
    type: "context",
    elements: [
      { type: "mrkdwn", text: "Add new path: `/trust /path/to/folder`" },
    ],
  });

  return blocks;
}
